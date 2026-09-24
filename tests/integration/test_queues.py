"""Integration tests for queue metrics endpoint."""
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
async def test_get_queues_admin(client, admin_user):
    token = await _login(client, "admin@example.com", "AdminPass1!")
    resp = await client.get(
        "/api/v1/queues",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "queues" in data


@pytest.mark.asyncio
async def test_get_queues_non_admin_allowed(client, regular_user):
    token = await _login(client, "user@example.com", "UserPass1!")
    resp = await client.get(
        "/api/v1/queues",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert "queues" in resp.json()


@pytest.mark.asyncio
async def test_get_queue_stats(client, admin_user, db_session):
    from datetime import datetime, timezone
    from uuid import uuid4

    from app.models.task import Task

    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            Task(
                id=uuid4(),
                user_id=admin_user.id,
                task_type="email_send",
                payload={},
                status="succeeded",
                started_at=now,
                completed_at=now,
            ),
            Task(
                id=uuid4(),
                user_id=admin_user.id,
                task_type="email_send",
                payload={},
                status="queued",
            ),
        ]
    )
    await db_session.commit()

    token = await _login(client, "admin@example.com", "AdminPass1!")
    resp = await client.get(
        "/api/v1/queues/stats",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status_counts"].get("queued", 0) >= 1
    assert data["status_counts"].get("succeeded", 0) >= 1
    assert "tasks_completed_per_minute_5m" in data["throughput"]
    assert "avg_pickup_seconds" in data["latency"]
    # must be a JSON number, not a Decimal-serialized string — dashboard calls .toFixed()
    assert isinstance(data["latency"]["avg_pickup_seconds"], (int, float))


@pytest.mark.asyncio
async def test_get_queue_stats_non_admin_allowed(client, regular_user):
    token = await _login(client, "user@example.com", "UserPass1!")
    resp = await client.get(
        "/api/v1/queues/stats",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert "status_counts" in resp.json()
