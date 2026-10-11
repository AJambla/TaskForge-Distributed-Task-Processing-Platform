"""Unit tests for idempotency replay semantics (IMP-05)."""
import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone
import uuid
from starlette.responses import Response

from app.models.task import Task
from app.models.user import User
from app.schemas.tasks import TaskCreateRequest, TaskType
from app.routers.tasks import create_task


@pytest.mark.asyncio
async def test_idempotency_duplicate_returns_existing_task_with_header():
    """Verify duplicate idempotency submission returns existing task and sets header."""
    user_id = uuid.uuid4()
    user = User(id=user_id, email="test@example.com", role="user")
    task_id = uuid.uuid4()
    existing_task = Task(
        id=task_id,
        user_id=user_id,
        task_type="email_send",
        payload={"to": "test@example.com", "subject": "Hi", "body": "Hello"},
        status="queued",
        priority=0,
        max_attempts=3,
        attempt_count=0,
        idempotency_key="key-123",
        created_at=datetime.now(timezone.utc),
    )

    body = TaskCreateRequest(
        task_type=TaskType.EMAIL_SEND,
        payload={"to": "test@example.com", "subject": "Hi", "body": "Hello"},
    )

    from unittest.mock import MagicMock
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing_task
    mock_db.execute.return_value = mock_result

    response = Response()

    with patch("app.routers.tasks.check_backpressure", new_callable=AsyncMock), \
         patch("app.routers.tasks.check_idempotency", return_value=True), \
         patch("app.routers.tasks.publish_task", new_callable=AsyncMock) as mock_pub:

        result = await create_task(
            body=body,
            current_user=user,
            db=mock_db,
            rate_limit=None,
            response=response,
            idempotency_key_header="key-123",
        )

        assert result.id == task_id
        assert response.headers.get("Idempotent-Replayed") == "true"
        mock_pub.assert_not_called()
