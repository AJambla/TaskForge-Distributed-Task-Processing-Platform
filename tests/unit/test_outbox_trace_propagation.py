"""Unit tests for Transactional Outbox traceparent persistence and relay forwarding (FEAT-03)."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task_outbox import TaskOutbox
from app.outbox.relay import OutboxRelayService
from app.outbox.service import create_outbox_event


@pytest.mark.asyncio
async def test_create_outbox_event_persists_traceparent():
    """Verify create_outbox_event stores traceparent column."""
    db = AsyncMock(spec=AsyncSession)
    task_id = uuid.uuid4()
    traceparent = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"

    event = await create_outbox_event(
        db=db,
        task_id=task_id,
        task_type="image_resize",
        payload={"width": 100, "height": 100},
        priority=2,
        traceparent=traceparent,
    )
    assert event.traceparent == traceparent
    db.add.assert_called_once_with(event)


@pytest.mark.asyncio
async def test_relay_forwards_traceparent_to_rabbitmq():
    """Verify outbox relay publishes to rabbitmq passing the stored traceparent."""
    event = TaskOutbox(
        id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        task_type="email_send",
        payload={"to": "a@b.com"},
        priority=1,
        traceparent="00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
        status="pending",
    )

    mock_db = AsyncMock(spec=AsyncSession)
    service = OutboxRelayService(session_factory=lambda: mock_db)

    with patch("app.outbox.relay.claim_pending_events", return_value=[event]), \
         patch("app.outbox.relay.publish_task", new_callable=AsyncMock) as mock_pub, \
         patch("app.outbox.relay.mark_published", new_callable=AsyncMock) as mock_mark:

        mock_db.__aenter__.return_value = mock_db
        count = await service.run_once()

        assert count == 1
        mock_pub.assert_called_once_with(
            task_id=str(event.task_id),
            task_type="email_send",
            priority=1,
            traceparent="00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
        )
        mock_mark.assert_called_once_with(mock_db, event.id)
