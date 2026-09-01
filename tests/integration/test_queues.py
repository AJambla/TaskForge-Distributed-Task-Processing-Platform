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
async def test_get_queues_non_admin_forbidden(client, regular_user):
    token = await _login(client, "user@example.com", "UserPass1!")
    resp = await client.get(
        "/api/v1/queues",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
