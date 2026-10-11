"""Unit tests for Transactional Outbox pattern (IMP-12)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
from datetime import datetime, timezone

from app.models.task import Task
from app.models.task_outbox import TaskOutbox
from app.models.user import User
from app.schemas.tasks import TaskCreateRequest, TaskType
from app.routers.tasks import create_task
from app.core.outbox import drain_outbox


@pytest.mark.asyncio
async def test_create_task_writes_task_and_outbox():
    user = User(id=uuid.uuid4(), email="user@example.com", role="user")
    body = TaskCreateRequest(
        task_type=TaskType.EMAIL_SEND,
        payload={"to": "user@example.com", "subject": "Test", "body": "Body"},
        priority=5,
    )

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()

    async def mock_refresh(task_obj):
        task_obj.id = uuid.uuid4()
        task_obj.status = "queued"
        task_obj.attempt_count = 0
        task_obj.idempotency_key = None
        task_obj.created_at = datetime.now(timezone.utc)

    mock_db.refresh = AsyncMock(side_effect=mock_refresh)

    with patch("app.routers.tasks.check_backpressure", new_callable=AsyncMock), \
         patch("app.routers.tasks.check_idempotency", return_value=False), \
         patch("app.routers.tasks.publish_task", new_callable=AsyncMock) as mock_pub, \
         patch("app.routers.tasks.set_idempotency_task_id", new_callable=AsyncMock):

        response = await create_task(
            body=body,
            current_user=user,
            db=mock_db,
            rate_limit=None,
        )

        assert mock_db.add.call_count == 2
        # Check that one added item is Task and other is TaskOutbox
        added_types = [type(call[0][0]) for call in mock_db.add.call_args_list]
        assert Task in added_types
        assert TaskOutbox in added_types
        assert mock_pub.called


@pytest.mark.asyncio
async def test_drain_outbox_relays_pending_messages():
    mock_db = AsyncMock()
    record1 = TaskOutbox(
        id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        task_type="email_send",
        payload={"to": "a@b.com"},
        priority=0,
        status="pending",
    )
    record2 = TaskOutbox(
        id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        task_type="image_resize",
        payload={"source_url": "http://img.png"},
        priority=10,
        status="pending",
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [record1, record2]
    mock_db.execute.return_value = mock_result
    records_by_id = {record1.id: record1, record2.id: record2}
    mock_db.get = AsyncMock(side_effect=lambda model, rid: records_by_id.get(rid))

    with patch("app.core.outbox.publish_task", new_callable=AsyncMock) as mock_pub:
        drained = await drain_outbox(mock_db, limit=10)

        assert drained == 2
        assert mock_pub.call_count == 2
        assert record1.status == "published"
        assert record2.status == "published"
        assert mock_db.commit.called
