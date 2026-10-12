"""Unit tests for task cancellation hardening (Phase 3)."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
import pytest
from fastapi import HTTPException

from app.models.task import Task
from app.routers.tasks import cancel_task
from app.worker.context import TaskContext
from app.worker import main as worker_main


@pytest.mark.asyncio
async def test_cancel_queued_task():
    """Verify queued task can be cancelled immediately."""
    task_id = uuid.uuid4()
    user_id = uuid.uuid4()
    task = Task(
        id=task_id,
        user_id=user_id,
        task_type="email_send",
        payload={},
        status="queued",
        priority=0,
        max_attempts=3,
        attempt_count=0,
        created_at=datetime.now(timezone.utc),
    )

    db = MagicMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = task
    db.execute = AsyncMock(return_value=mock_res)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    current_user = MagicMock()
    current_user.id = user_id
    current_user.role = "user"

    resp = await cancel_task(task_id, current_user, db)

    assert resp.status == "cancelled"
    assert task.status == "cancelled"
    assert task.completed_at is not None
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancel_running_task_sets_redis_flag():
    """Verify running task sets Redis cooperative cancellation flag."""
    task_id = uuid.uuid4()
    user_id = uuid.uuid4()
    task = Task(
        id=task_id,
        user_id=user_id,
        task_type="webhook_delivery",
        payload={},
        status="running",
        priority=0,
        max_attempts=3,
        attempt_count=1,
        created_at=datetime.now(timezone.utc),
    )

    db = MagicMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = task
    db.execute = AsyncMock(return_value=mock_res)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    current_user = MagicMock()
    current_user.id = user_id
    current_user.role = "user"

    mock_redis = AsyncMock()
    with patch("app.core.redis.get_redis", return_value=mock_redis):
        resp = await cancel_task(task_id, current_user, db)

    assert resp.status == "cancelled"
    assert task.status == "cancelled"
    assert task.completed_at is not None
    mock_redis.set.assert_awaited_once_with(f"task:cancelled:{task_id}", "1", ex=3600)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancel_terminal_task_raises_conflict():
    """Verify attempting to cancel a succeeded task raises 409 Conflict."""
    task_id = uuid.uuid4()
    user_id = uuid.uuid4()
    task = Task(
        id=task_id,
        user_id=user_id,
        task_type="email_send",
        payload={},
        status="succeeded",
        priority=0,
        max_attempts=3,
    )

    db = MagicMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = task
    db.execute = AsyncMock(return_value=mock_res)

    current_user = MagicMock()
    current_user.id = user_id
    current_user.role = "user"

    with pytest.raises(HTTPException) as exc_info:
        await cancel_task(task_id, current_user, db)

    assert exc_info.value.status_code == 409
    assert "cannot be cancelled" in exc_info.value.detail["error"]["message"]


@pytest.mark.asyncio
async def test_task_context_is_cancelled():
    """Verify TaskContext.is_cancelled checks Redis flag."""
    task_id = str(uuid.uuid4())
    ctx = TaskContext(task_id=task_id, task_type="email_send")

    mock_redis = AsyncMock()
    mock_redis.exists.return_value = 1

    with patch("app.worker.context.get_redis", return_value=mock_redis):
        cancelled = await ctx.is_cancelled()
        assert cancelled is True
        mock_redis.exists.assert_awaited_once_with(f"task:cancelled:{task_id}")


@pytest.mark.asyncio
async def test_consume_task_aborts_on_cancellation():
    """Verify consume_task detects cancellation and does not execute handler."""
    task_id = uuid.uuid4()
    task = Task(
        id=task_id,
        user_id=uuid.uuid4(),
        task_type="webhook_delivery",
        payload={},
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

    handler_called = False

    async def sample_handler(payload, ctx=None):
        nonlocal handler_called
        handler_called = True
        return {"ok": True}

    with patch("app.worker.main.get_handler", return_value=sample_handler), \
         patch("app.worker.context.TaskContext.is_cancelled", new_callable=AsyncMock) as mock_is_canc:
        mock_is_canc.return_value = True

        status, attempts, max_att, defer = await worker_main.consume_task(
            db=db,
            task_id=str(task_id),
            task_type="webhook_delivery",
        )

        assert status == "cancelled"
        assert handler_called is False
        assert task.status == "cancelled"
