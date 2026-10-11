"""Unit tests for Bulk Task Ingestion endpoint (IMP-17)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
from datetime import datetime, timezone

from app.models.user import User
from app.schemas.tasks import TaskBulkCreateRequest, TaskCreateRequest, TaskType
from app.routers.tasks import create_tasks_bulk


@pytest.mark.asyncio
async def test_create_tasks_bulk_success():
    user = User(id=uuid.uuid4(), email="bulk@example.com", role="user")
    tasks_input = [
        TaskCreateRequest(
            task_type=TaskType.EMAIL_SEND,
            payload={"to": f"user{i}@example.com", "subject": f"Sub {i}", "body": "Body"},
            priority=i,
        )
        for i in range(5)
    ]
    body = TaskBulkCreateRequest(tasks=tasks_input)

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()

    # Simulate flushing task IDs
    def mock_add(obj):
        if not hasattr(obj, "id") or obj.id is None:
            obj.id = uuid.uuid4()
            obj.status = "queued"
            obj.attempt_count = 0
            obj.created_at = datetime.now(timezone.utc)

    mock_db.add.side_effect = mock_add

    with patch("app.routers.tasks.check_backpressure", new_callable=AsyncMock), \
         patch("app.routers.tasks.publish_task", new_callable=AsyncMock) as mock_pub:

        res = await create_tasks_bulk(body=body, current_user=user, db=mock_db)

        assert res.submitted_count == 5
        assert len(res.tasks) == 5
        assert mock_pub.call_count == 5
        assert mock_db.commit.call_count >= 2
