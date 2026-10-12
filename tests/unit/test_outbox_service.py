"""Unit tests for Outbox database service, exponential backoff, and pruning (FEAT-02)."""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.models.task_outbox import TaskOutbox
from app.outbox.service import (
    create_outbox_event,
    mark_published,
    mark_failed,
    calculate_backoff_seconds,
)


def test_calculate_backoff_exponential():
    assert calculate_backoff_seconds(0) == 1
    assert calculate_backoff_seconds(1) == 2
    assert calculate_backoff_seconds(2) == 4
    assert calculate_backoff_seconds(3) == 8
    assert calculate_backoff_seconds(4) == 16
    assert calculate_backoff_seconds(10) == 300  # Clamped at 300


@pytest.mark.asyncio
async def test_create_outbox_event():
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    task_id = uuid.uuid4()

    event = await create_outbox_event(
        db=mock_db,
        task_id=task_id,
        task_type="image_resize",
        payload={"source_url": "https://example.com/img.png"},
        priority=5,
        event_type="task_created",
    )

    assert mock_db.add.called
    assert event.task_id == task_id
    assert event.task_type == "image_resize"
    assert event.priority == 5
    assert event.status == "pending"
    assert event.retry_count == 0


@pytest.mark.asyncio
async def test_mark_published_updates_status():
    mock_db = AsyncMock()
    event = TaskOutbox(
        id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        task_type="email_send",
        payload={},
        status="pending",
    )
    mock_db.get = AsyncMock(return_value=event)

    await mark_published(mock_db, event.id)

    assert event.status == "published"
    assert event.processed_at is not None
    assert mock_db.commit.called


@pytest.mark.asyncio
async def test_mark_failed_with_backoff():
    mock_db = AsyncMock()
    event = TaskOutbox(
        id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        task_type="email_send",
        payload={},
        status="pending",
        retry_count=2,
    )
    mock_db.get = AsyncMock(return_value=event)

    await mark_failed(mock_db, event.id, error="Broker timeout", max_retries=5)

    assert event.retry_count == 3
    assert event.status == "pending"
    assert event.last_error == "Broker timeout"
    assert event.last_attempt_at is not None
    assert event.next_attempt_at > event.last_attempt_at
    assert mock_db.commit.called


@pytest.mark.asyncio
async def test_mark_failed_transitions_to_failed_at_max_retries():
    mock_db = AsyncMock()
    event = TaskOutbox(
        id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        task_type="email_send",
        payload={},
        status="pending",
        retry_count=4,
    )
    mock_db.get = AsyncMock(return_value=event)

    await mark_failed(mock_db, event.id, error="Fatal network error", max_retries=5)

    assert event.retry_count == 5
    assert event.status == "failed"
    assert event.last_error == "Fatal network error"
    assert mock_db.commit.called
