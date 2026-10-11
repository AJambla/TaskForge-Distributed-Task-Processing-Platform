"""Unit tests for task result persistence (IMP-02)."""
import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone
import uuid

from app.models.task import Task
from app.models.task_attempt import TaskAttempt
from app.schemas.tasks import TaskResponse
from app.worker.main import _mark_success


def test_task_model_has_result_field():
    """Verify Task and TaskAttempt have a result attribute defaulting to None."""
    task = Task(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        task_type="email_send",
        payload={"to": "test@example.com"},
    )
    assert hasattr(task, "result")
    assert task.result is None

    attempt = TaskAttempt(
        task_id=task.id,
        attempt_number=1,
    )
    assert hasattr(attempt, "result")
    assert attempt.result is None


def test_task_response_schema_serializes_result():
    """Verify TaskResponse schema accepts and serializes result field."""
    task_id = uuid.uuid4()
    user_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    res_data = {"format": "PNG", "size_bytes": 1024, "output_path": "data/images/test.png"}

    task = Task(
        id=task_id,
        user_id=user_id,
        task_type="image_resize",
        payload={"source_url": "http://example.com/test.png"},
        status="succeeded",
        priority=0,
        idempotency_key=None,
        max_attempts=3,
        attempt_count=1,
        created_at=now,
        completed_at=now,
        result=res_data,
    )

    resp = TaskResponse.model_validate(task)
    assert resp.result == res_data


@pytest.mark.asyncio
async def test_mark_success_persists_result():
    """Verify _mark_success sets result on both task and attempt."""
    db = AsyncMock()
    task = Task(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        task_type="email_send",
        payload={"to": "test@example.com"},
        attempt_count=1,
    )
    attempt = TaskAttempt(
        task_id=task.id,
        attempt_number=1,
    )
    output = {"sent": True, "message_id": "msg_123"}

    await _mark_success(db, task, attempt, result=output)

    assert task.status == "succeeded"
    assert task.result == output
    assert attempt.outcome == "success"
    assert attempt.result == output
    db.commit.assert_awaited_once()
