"""Integration tests for worker admin endpoints."""
from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def _login(client, email: str, password: str) -> str:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_list_workers_admin(client, worker, admin_user):
    token = await _login(client, "admin@example.com", "AdminPass1!")
    resp = await client.get(
        "/api/v1/workers",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["hostname"] == "test-worker-1"


@pytest.mark.asyncio
async def test_list_workers_non_admin_forbidden(client, regular_user):
    token = await _login(client, "user@example.com", "UserPass1!")
    resp = await client.get(
        "/api/v1/workers",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_worker_detail(client, worker, admin_user):
    token = await _login(client, "admin@example.com", "AdminPass1!")
    resp = await client.get(
        f"/api/v1/workers/{worker.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(worker.id)
    assert data["hostname"] == "test-worker-1"
    assert "recent_attempts" in data


@pytest.mark.asyncio
async def test_get_worker_not_found(client, admin_user):
    import uuid
    token = await _login(client, "admin@example.com", "AdminPass1!")
    resp = await client.get(
        f"/api/v1/workers/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_stale_heartbeat_worker_reported_offline(
    client, admin_user, db_session
):
    """A worker that stopped heartbeating must not show as online."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from app.models.worker_registration import WorkerRegistration

    stale_beat = datetime.now(timezone.utc) - timedelta(minutes=10)
    dead = WorkerRegistration(
        hostname="crashed-worker",
        status="online",
        concurrency_limit=4,
        last_heartbeat_at=stale_beat,
    )
    db_session.add(dead)
    await db_session.commit()

    token = await _login(client, "admin@example.com", "AdminPass1!")
    resp = await client.get(
        "/api/v1/workers",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    entry = next(w for w in resp.json() if w["hostname"] == "crashed-worker")
    assert entry["status"] == "offline"

    # The sweep committed via the app's session; drop this session's
    # cached copies so the re-read hits the database.
    db_session.expire_all()
    result = await db_session.execute(
        select(WorkerRegistration).where(
            WorkerRegistration.hostname == "crashed-worker"
        )
    )
    stored = result.scalar_one()
    assert stored.status == "offline"
    # The sweep must preserve when the worker was actually last seen.
    assert stored.last_heartbeat_at < datetime.now(timezone.utc) - timedelta(minutes=9)
