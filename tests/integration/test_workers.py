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
