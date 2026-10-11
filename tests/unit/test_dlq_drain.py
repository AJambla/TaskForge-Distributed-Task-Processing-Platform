"""Unit tests for DLQ drain on redrive (IMP-10)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
from datetime import datetime, timezone

from app.models.task import Task
from app.models.user import User
from app.routers.queues import redrive_dlq


@pytest.mark.asyncio
async def test_redrive_dlq_purges_rabbitmq_dlqs():
    user = User(id=uuid.uuid4(), email="admin@example.com", role="admin")
    task1 = Task(
        id=uuid.uuid4(),
        user_id=user.id,
        task_type="email_send",
        payload={"to": "test@example.com", "subject": "Hi", "body": "Test"},
        status="dead_letter",
        priority=0,
        completed_at=datetime.now(timezone.utc),
    )
    task2 = Task(
        id=uuid.uuid4(),
        user_id=user.id,
        task_type="image_resize",
        payload={"source_url": "http://img.jpg", "width": 100, "height": 100},
        status="dead_letter",
        priority=0,
        completed_at=datetime.now(timezone.utc),
    )

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [task1, task2]
    mock_db.execute.return_value = mock_result

    with patch("app.routers.queues.publish_task", new_callable=AsyncMock) as mock_pub, \
         patch("app.routers.queues.purge_queue", new_callable=AsyncMock) as mock_purge:

        res = await redrive_dlq(current_user=user, db=mock_db, limit=50)

        assert res["redriven_count"] == 2
        assert mock_pub.call_count == 2
        assert mock_db.commit.called

        # Verify purge_queue was called for both affected task types
        mock_purge.assert_any_call("tasks.email_send.dlq")
        mock_purge.assert_any_call("tasks.image_resize.dlq")
        assert mock_purge.call_count == 2
