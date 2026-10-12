"""Unit tests for task execution timeout enforcement (Phase 3)."""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
import pytest

from app.models.task import Task
from app.worker.executor import get_timeout
from app.worker import main as worker_main


def test_get_timeout_payload_override():
    """Verify that task payload can override default task timeout."""
    # Default without payload
    default_timeout = get_timeout("webhook_delivery", {})
    assert default_timeout == 30

    # Override via timeout_seconds
    override_1 = get_timeout("webhook_delivery", {"timeout_seconds": 12})
    assert override_1 == 12

    # Override via timeout
    override_2 = get_timeout("email_send", {"timeout": 45})
    assert override_2 == 45

    # Invalid values fall back safely
    fallback = get_timeout("webhook_delivery", {"timeout_seconds": "invalid"})
    assert fallback == 30


@pytest.mark.asyncio
async def test_consume_task_timeout_records_attempt_and_retries():
    """Verify that handler exceeding timeout records deterministic error and transitions to retrying."""
    task_id = uuid.uuid4()
    worker_id = uuid.uuid4()
    task = Task(
        id=task_id,
        user_id=uuid.uuid4(),
        task_type="webhook_delivery",
        payload={"timeout_seconds": 1},
        status="queued",
        priority=0,
        max_attempts=3,
        attempt_count=0,
        created_at=datetime.now(timezone.utc),
        attempts=[],
    )

    db = MagicMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = task
    db.execute = AsyncMock(return_value=mock_res)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()

    # Sleep longer than the 1s timeout
    async def slow_handler(payload):
        await asyncio.sleep(2)
        return {"status": "too_late"}

    with patch("app.worker.main.get_handler", return_value=slow_handler), \
         patch("app.worker.main._mark_failure", new_callable=AsyncMock) as mock_failure:

        status, attempts, max_att, defer = await worker_main.consume_task(
            db=db,
            task_id=str(task_id),
            task_type="webhook_delivery",
            worker_id=worker_id,
        )

        assert status == "timeout"
        assert attempts == 1
        assert max_att == 3

        mock_failure.assert_awaited_once()
        call_args = mock_failure.call_args
        assert call_args.args[3] == "timeout"  # outcome
        assert "Task exceeded execution timeout of 1s" in call_args.kwargs["error_message"]
        assert call_args.kwargs["error_detail"]["error_type"] == "TimeoutError"
        assert call_args.kwargs["error_detail"]["timeout_seconds"] == 1
