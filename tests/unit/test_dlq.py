"""Unit tests for DLQ inspection and redrive endpoints."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routers import queues as queues_router


@pytest.mark.asyncio
async def test_inspect_dlq():
    db = MagicMock()
    mock_task = MagicMock()
    mock_task.id = uuid.uuid4()
    mock_task.task_type = "email_send"
    mock_task.attempt_count = 5
    mock_task.created_at = None
    mock_task.completed_at = None

    result = MagicMock()
    result.scalars.return_value.all.return_value = [mock_task]
    db.execute = AsyncMock(return_value=result)

    with patch("app.routers.queues.get_queue_depths", AsyncMock(return_value={"tasks.email_send.dlq": 3})):
        user = MagicMock()
        user.role = "admin"
        res = await queues_router.inspect_dlq(current_user=user, db=db)
        assert res["dead_letter_count"] == 1
        assert res["dlq_depths"] == {"tasks.email_send.dlq": 3}
        assert len(res["recent_dead_tasks"]) == 1


@pytest.mark.asyncio
async def test_redrive_dlq():
    db = MagicMock()
    db.commit = AsyncMock()
    mock_task = MagicMock()
    mock_task.id = uuid.uuid4()
    mock_task.task_type = "email_send"

    result = MagicMock()
    result.scalars.return_value.all.return_value = [mock_task]
    db.execute = AsyncMock(return_value=result)

    with patch("app.routers.queues.publish_task", AsyncMock()) as mock_pub:
        user = MagicMock()
        user.role = "admin"
        res = await queues_router.redrive_dlq(current_user=user, db=db, limit=10)
        assert res["redriven_count"] == 1
        assert mock_task.status == "queued"
        assert mock_task.attempt_count == 0
        mock_pub.assert_awaited_once_with(str(mock_task.id), "email_send")
        db.commit.assert_awaited_once()
