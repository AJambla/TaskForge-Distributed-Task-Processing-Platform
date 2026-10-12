"""Unit tests for Outbox Relay Runner Service (FEAT-02)."""
import uuid
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.task_outbox import TaskOutbox
from app.outbox.relay import OutboxRelayService


@pytest.mark.asyncio
async def test_relay_service_run_once_relays_events():
    mock_session_factory = MagicMock()
    mock_db = AsyncMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_db

    event1 = TaskOutbox(
        id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        task_type="email_send",
        payload={"to": "dev@test.com"},
        priority=0,
        status="pending",
        created_at=datetime.now(timezone.utc),
    )

    with patch("app.outbox.relay.claim_pending_events", new_callable=AsyncMock) as mock_claim, \
         patch("app.outbox.relay.publish_task", new_callable=AsyncMock) as mock_pub, \
         patch("app.outbox.relay.mark_published", new_callable=AsyncMock) as mock_mark:

        mock_claim.return_value = [event1]

        service = OutboxRelayService(session_factory=mock_session_factory, batch_size=10)
        relayed = await service.run_once()

        assert relayed == 1
        assert mock_pub.called
        assert mock_mark.called


@pytest.mark.asyncio
async def test_relay_service_handles_publish_failure():
    mock_session_factory = MagicMock()
    mock_db = AsyncMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_db

    event1 = TaskOutbox(
        id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        task_type="email_send",
        payload={"to": "dev@test.com"},
        priority=0,
        status="pending",
        created_at=datetime.now(timezone.utc),
    )

    with patch("app.outbox.relay.claim_pending_events", new_callable=AsyncMock) as mock_claim, \
         patch("app.outbox.relay.publish_task", side_effect=RuntimeError("RabbitMQ is down")), \
         patch("app.outbox.relay.mark_failed", new_callable=AsyncMock) as mock_fail:

        mock_claim.return_value = [event1]

        service = OutboxRelayService(session_factory=mock_session_factory, batch_size=10)
        relayed = await service.run_once()

        assert relayed == 0
        assert mock_fail.called
