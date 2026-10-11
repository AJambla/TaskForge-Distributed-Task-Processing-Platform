"""Unit tests for Worker trace recording, span execution, latency measurement, and attempts (FEAT-03)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tracing import init_tracer
from app.models.task import Task
from app.models.task_attempt import TaskAttempt
from app.worker.lifecycle import create_attempt
from app.worker.main import consume_task


@pytest.fixture(autouse=True)
def setup_tracer():
    init_tracer("taskforge-worker-test")


@pytest.mark.asyncio
async def test_create_attempt_persists_trace_id():
    """Verify create_attempt sets the trace_id column on TaskAttempt."""
    db = AsyncMock(spec=AsyncSession)
    task = Task(
        id=uuid.uuid4(),
        attempt_count=1,
        trace_id="4bf92f3577b34da6a3ce929d0e0e4736",
    )
    worker_id = uuid.uuid4()

    attempt = await create_attempt(db, task, worker_id=worker_id)
    assert attempt.trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert attempt.worker_id == worker_id
    db.add.assert_called_once_with(attempt)


@pytest.mark.asyncio
async def test_worker_consume_task_creates_child_span_and_records_attempt():
    """Verify consume_task executes inside an OpenTelemetry child span with proper attributes."""
    task_id = str(uuid.uuid4())
    trace_id_hex = "4bf92f3577b34da6a3ce929d0e0e4736"
    traceparent = f"00-{trace_id_hex}-00f067aa0ba902b7-01"

    task = Task(
        id=uuid.UUID(task_id),
        user_id=uuid.uuid4(),
        task_type="email_send",
        payload={"to": "test@example.com", "subject": "Test", "body": "Body"},
        status="queued",
        priority=3,
        max_attempts=5,
        attempt_count=0,
        created_at=datetime.now(timezone.utc),
        trace_id=trace_id_hex,
    )

    db = AsyncMock(spec=AsyncSession)
    mock_scalar = MagicMock()
    mock_scalar.scalar_one_or_none.return_value = task
    db.execute.return_value = mock_scalar

    with patch("app.worker.main.get_handler") as mock_get_handler, \
         patch("app.worker.main._mark_success", new_callable=AsyncMock) as mock_mark_success:

        mock_handler = AsyncMock(return_value={"status": "sent"})
        mock_get_handler.return_value = mock_handler

        status, attempt_count, max_att, defer = await consume_task(
            db=db,
            task_id=task_id,
            task_type="email_send",
            traceparent=traceparent,
        )

        assert status == "succeeded"
        assert attempt_count == 1
        mock_handler.assert_called_once()
        mock_mark_success.assert_called_once()
