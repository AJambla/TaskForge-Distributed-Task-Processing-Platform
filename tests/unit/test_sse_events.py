"""Unit tests for Server-Sent Events (SSE) streaming (IMP-19)."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.models.task import Task
from app.models.user import User
from app.routers.tasks import stream_task_events
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_stream_task_events_404_when_not_found():
    user = User(id=uuid.uuid4(), email="user@example.com", role="user")
    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_res

    with pytest.raises(HTTPException) as exc_info:
        await stream_task_events(task_id=uuid.uuid4(), current_user=user, db=mock_db)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_stream_task_events_terminal_task_yields_initial_and_closes():
    user = User(id=uuid.uuid4(), email="user@example.com", role="user")
    task_id = uuid.uuid4()
    task = Task(
        id=task_id,
        user_id=user.id,
        task_type="email_send",
        status="succeeded",
        priority=0,
        max_attempts=3,
        attempt_count=1,
        created_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        result={"status": "sent"},
    )

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = task
    mock_db.execute.return_value = mock_res

    response = await stream_task_events(task_id=task_id, current_user=user, db=mock_db)
    assert response.media_type == "text/event-stream"

    # Consume the generator
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    assert len(chunks) == 1
    assert "data: " in chunks[0]
    payload = json.loads(chunks[0].replace("data: ", "").strip())
    assert payload["task_id"] == str(task_id)
    assert payload["status"] == "succeeded"
    assert payload["result"] == {"status": "sent"}
