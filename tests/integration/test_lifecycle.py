"""Integration tests for full task execution lifecycle and failure recovery (M-07)."""
from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.main import app
from app.models.task import Task
from app.models.task_attempt import TaskAttempt
from app.models.worker_registration import WorkerRegistration
from app.worker.main import consume_task


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
async def test_task_lifecycle_success(client, regular_user, db_session, monkeypatch):
    """Verify task flows from queued -> running -> succeeded with attempt record."""
    # Mock handler to complete successfully without external network dependencies
    async def fake_handler(payload):
        return {"status": "ok", "delivered": True}

    monkeypatch.setattr("app.worker.main.get_handler", lambda t: fake_handler)

    token = await _login(client, "user@example.com", "UserPass1!")

    # 1. Create task via API
    resp = await client.post(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "task_type": "email_send",
            "payload": {
                "to": "test@example.com",
                "subject": "Lifecycle Test",
                "body": "Hello World",
            },
        },
    )
    assert resp.status_code in (201, 503)
    task_id = resp.json()["id"]

    # Register worker in DB
    worker = WorkerRegistration(hostname="test-worker", status="online", concurrency_limit=5)
    db_session.add(worker)
    await db_session.commit()
    await db_session.refresh(worker)

    # 2. Worker consumes task
    status, attempt_count, max_attempts, defer_sec = await consume_task(
        db_session, task_id, "email_send", worker_id=worker.id
    )
    assert status == "succeeded"
    assert attempt_count == 1

    # 3. Verify task & attempt state in DB
    res = await db_session.execute(
        select(Task).where(Task.id == task_id).options(selectinload(Task.attempts))
    )
    t = res.scalar_one()
    assert t.status == "succeeded"
    assert t.attempt_count == 1
    assert t.started_at is not None
    assert t.completed_at is not None
    assert len(t.attempts) == 1
    assert t.attempts[0].outcome == "success"
    assert t.attempts[0].worker_id == worker.id
    assert t.attempts[0].finished_at is not None


@pytest.mark.asyncio
async def test_task_lifecycle_failure_and_retry(client, regular_user, db_session, monkeypatch):
    """Verify task retry transition when a handler fails up to max_attempts."""
    async def failing_handler(payload):
        raise RuntimeError("Handler execution simulated failure")

    monkeypatch.setattr("app.worker.main.get_handler", lambda t: failing_handler)

    token = await _login(client, "user@example.com", "UserPass1!")

    resp = await client.post(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "task_type": "webhook_delivery",
            "payload": {"url": "https://example.com/fail"},
            "max_attempts": 2,
        },
    )
    assert resp.status_code in (201, 503)
    task_id = resp.json()["id"]

    worker = WorkerRegistration(hostname="test-worker-fail", status="online", concurrency_limit=5)
    db_session.add(worker)
    await db_session.commit()
    await db_session.refresh(worker)

    # Attempt 1 -> consume_task returns "failed" (outcome), DB task status is updated to "retrying"
    status, attempt_count, max_attempts, defer_sec = await consume_task(
        db_session, task_id, "webhook_delivery", worker_id=worker.id
    )
    assert status == "failed"
    assert attempt_count == 1
    assert attempt_count < max_attempts

    res = await db_session.execute(
        select(Task).where(Task.id == task_id).options(selectinload(Task.attempts))
    )
    t = res.scalar_one()
    assert t.status == "retrying"
    assert len(t.attempts) == 1
    assert t.attempts[0].outcome == "failure"
    assert "Handler execution simulated failure" in (t.attempts[0].error_message or "")

    # Attempt 2 -> hits max_attempts, DB status transitions to "failed"
    status, attempt_count, max_attempts, defer_sec = await consume_task(
        db_session, task_id, "webhook_delivery", worker_id=worker.id
    )
    assert status == "failed"
    assert attempt_count == 2
    assert attempt_count >= max_attempts

    db_session.expire_all()
    res = await db_session.execute(
        select(Task).where(Task.id == task_id).options(selectinload(Task.attempts))
    )
    t = res.scalar_one()
    assert t.status == "failed"
    assert len(t.attempts) == 2
    assert t.attempts[1].outcome == "failure"
