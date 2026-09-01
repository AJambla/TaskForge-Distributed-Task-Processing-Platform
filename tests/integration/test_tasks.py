"""Integration tests for task endpoints."""
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
async def test_create_task(client, regular_user):
    token = await _login(client, "user@example.com", "UserPass1!")
    resp = await client.post(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "task_type": "email_send",
            "payload": {
                "to": "recipient@example.com",
                "subject": "Test",
                "body": "Hello",
            },
        },
    )
    # Task creation may fail if RabbitMQ is not available, but the endpoint should exist
    assert resp.status_code in (201, 503)


@pytest.mark.asyncio
async def test_list_tasks(client, regular_user):
    token = await _login(client, "user@example.com", "UserPass1!")
    resp = await client.get(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert "pagination" in data


@pytest.mark.asyncio
async def test_get_task_not_found(client, regular_user):
    token = await _login(client, "user@example.com", "UserPass1!")
    import uuid
    resp = await client.get(
        f"/api/v1/tasks/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_sees_all_tasks(client, admin_user, regular_user):
    admin_token = await _login(client, "admin@example.com", "AdminPass1!")
    resp = await client.get(
        "/api/v1/tasks?all_tasks=true",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200

    # Regular user should not be able to use all_tasks
    user_token = await _login(client, "user@example.com", "UserPass1!")
    resp = await client.get(
        "/api/v1/tasks?all_tasks=true",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 403
