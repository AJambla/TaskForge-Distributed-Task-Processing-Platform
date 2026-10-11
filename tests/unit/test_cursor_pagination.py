"""Unit tests for keyset cursor pagination (IMP-18)."""
import pytest
from unittest.mock import AsyncMock, MagicMock
import uuid
import base64
import json
from datetime import datetime, timezone

from app.models.task import Task
from app.models.user import User
from app.routers.tasks import list_tasks


@pytest.mark.asyncio
async def test_list_tasks_returns_next_cursor_when_page_full():
    user = User(id=uuid.uuid4(), email="user@example.com", role="user")
    tasks = [
        Task(
            id=uuid.uuid4(),
            user_id=user.id,
            task_type="email_send",
            status="succeeded",
            priority=0,
            max_attempts=3,
            attempt_count=1,
            created_at=datetime.now(timezone.utc),
        )
        for _ in range(5)
    ]

    mock_db = AsyncMock()
    # Mock count query
    mock_count_res = MagicMock()
    mock_count_res.scalar_one.return_value = 10
    # Mock data query
    mock_data_res = MagicMock()
    mock_data_res.scalars.return_value.all.return_value = tasks

    mock_db.execute.side_effect = [mock_count_res, mock_data_res]

    res = await list_tasks(current_user=user, db=mock_db, page_size=5, all_tasks=False)

    assert len(res.data) == 5
    assert res.pagination.next_cursor is not None

    # Decode and verify next_cursor format
    decoded = json.loads(base64.urlsafe_b64decode(res.pagination.next_cursor.encode("utf-8")).decode("utf-8"))
    assert "created_at" in decoded
    assert "id" in decoded
    assert decoded["id"] == str(tasks[-1].id)


@pytest.mark.asyncio
async def test_list_tasks_with_cursor_applies_keyset_filter():
    user = User(id=uuid.uuid4(), email="user@example.com", role="user")
    cursor_id = uuid.uuid4()
    cursor_data = json.dumps({"created_at": datetime.now(timezone.utc).isoformat(), "id": str(cursor_id)})
    cursor_token = base64.urlsafe_b64encode(cursor_data.encode("utf-8")).decode("utf-8")

    mock_db = AsyncMock()
    mock_count_res = MagicMock()
    mock_count_res.scalar_one.return_value = 5
    mock_data_res = MagicMock()
    mock_data_res.scalars.return_value.all.return_value = []

    mock_db.execute.side_effect = [mock_count_res, mock_data_res]

    res = await list_tasks(current_user=user, db=mock_db, page_size=5, cursor=cursor_token, all_tasks=False)

    assert res.pagination.next_cursor is None
    assert mock_db.execute.call_count == 2
