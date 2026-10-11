"""Unit tests for task ingestion trace propagation and schema trace URLs (FEAT-03)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.tracing import init_tracer
from app.main import app
from app.models.task import Task
from app.schemas.tasks import TaskResponse


@pytest.fixture(autouse=True)
def setup_tracer():
    init_tracer("taskforge-test")


def test_task_response_trace_url_interpolation():
    """Verify TaskResponse computes trace_url when trace_id is present."""
    task = Task(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        task_type="email_send",
        payload={"to": "test@example.com", "subject": "Hi", "body": "Hello"},
        status="queued",
        priority=0,
        max_attempts=5,
        attempt_count=0,
        created_at=datetime.now(timezone.utc),
        trace_id="4bf92f3577b34da6a3ce929d0e0e4736",
    )
    resp = TaskResponse.from_task(task)
    assert resp.trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert resp.trace_url == "http://localhost:16686/trace/4bf92f3577b34da6a3ce929d0e0e4736"


def test_task_response_null_trace_id():
    """Verify TaskResponse handles null trace_id gracefully without url."""
    task = Task(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        task_type="email_send",
        payload={"to": "test@example.com", "subject": "Hi", "body": "Hello"},
        status="queued",
        priority=0,
        max_attempts=5,
        attempt_count=0,
        created_at=datetime.now(timezone.utc),
        trace_id=None,
    )
    resp = TaskResponse.from_task(task)
    assert resp.trace_id is None
    assert resp.trace_url is None
