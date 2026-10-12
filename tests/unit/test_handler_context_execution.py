"""Unit tests for pluggable handler TaskContext worker invocation (FEAT-06 Task 2)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.worker.context import TaskContext
from app.worker.handlers import register_handler, HANDLER_REGISTRY, HANDLER_METADATA
from app.worker.main import consume_task


@pytest.mark.asyncio
async def test_consume_task_injects_context_and_records_progress():
    custom_type = f"test_ctx_{uuid4().hex[:6]}"
    invoked_with = {}

    @register_handler(custom_type)
    async def sample_handler(payload: dict, ctx: TaskContext):
        invoked_with["task_id"] = ctx.task_id
        invoked_with["task_type"] = ctx.task_type
        invoked_with["worker_id"] = ctx.worker_id
        invoked_with["attempt"] = ctx.attempt
        await ctx.set_progress(50, "Halfway done")
        return {"status": "ok", "processed": payload.get("val")}

    # Mock DB Task and Attempt
    task_id = uuid4()
    mock_task = MagicMock()
    mock_task.id = task_id
    mock_task.status = "pending"
    mock_task.payload = {"val": 42}
    mock_task.priority = 1
    mock_task.attempt_count = 0
    mock_task.max_attempts = 3
    mock_task.run_at = None
    mock_task.created_at = None
    mock_task.trace_id = "trace-123456"

    mock_attempt = MagicMock()
    mock_attempt.attempt_number = 1

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_task
    mock_db.execute.return_value = mock_result

    with patch("app.worker.main.create_attempt", AsyncMock(return_value=mock_attempt)), \
         patch("app.worker.main._mark_success", AsyncMock()) as mock_mark_success, \
         patch("app.worker.context.get_redis", AsyncMock()) as mock_get_redis:

        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        status, attempts, max_att, defer = await consume_task(
            mock_db,
            task_id=task_id,
            task_type=custom_type,
            worker_id="worker-test-1",
        )

        assert status == "succeeded"
        assert invoked_with["task_id"] == str(task_id)
        assert invoked_with["task_type"] == custom_type
        assert invoked_with["worker_id"] == "worker-test-1"
        assert invoked_with["attempt"] == 1
        # Redis publish should have been called for set_progress
        assert mock_redis.publish.called
        # Check mark success called with result
        assert mock_mark_success.called
        assert mock_mark_success.call_args[1]["result"]["status"] == "ok"

