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


@pytest.mark.asyncio
async def test_retry_rolls_back_when_publish_fails(
    client, regular_user, db_session, monkeypatch
):
    """A failed re-publish must not leave the task stranded in 'queued'."""
    from uuid import uuid4

    from sqlalchemy import select

    from app.models.task import Task

    task = Task(
        id=uuid4(),
        user_id=regular_user.id,
        task_type="email_send",
        payload={"to": "x@example.com", "subject": "s", "body": "b"},
        status="dead_letter",
        attempt_count=3,
        max_attempts=3,
    )
    db_session.add(task)
    await db_session.commit()

    async def _boom(*args, **kwargs):
        raise RuntimeError("broker down")

    monkeypatch.setattr("app.routers.tasks.publish_task", _boom)

    token = await _login(client, "user@example.com", "UserPass1!")
    resp = await client.post(
        f"/api/v1/tasks/{task.id}/retry",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 503

    result = await db_session.execute(select(Task).where(Task.id == task.id))
    stored = result.scalar_one()
    assert stored.status == "dead_letter"
    assert stored.attempt_count == 3
