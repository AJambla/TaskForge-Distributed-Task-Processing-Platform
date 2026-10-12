"""Unit tests for Transactional Outbox concurrency and SKIP LOCKED hardening (Phase 3)."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
import pytest

from app.models.task_outbox import TaskOutbox
from app.outbox.relay import OutboxRelayService
from app.outbox.service import claim_pending_events, mark_published, mark_failed


@pytest.mark.asyncio
async def test_claim_pending_events_specifies_for_update_skip_locked():
    """Verify that claim_pending_events compiles with FOR UPDATE SKIP LOCKED."""
    db = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=mock_result)

    await claim_pending_events(db, batch_size=25)

    assert db.execute.called
    stmt = db.execute.call_args[0][0]
    # Check SQLAlchemy statement modifier
    assert stmt._for_update_arg is not None
    assert stmt._for_update_arg.skip_locked is True


@pytest.mark.asyncio
async def test_concurrent_relay_workers_partition_events_without_duplication():
    """Simulate two concurrent relay workers running run_once and asserting disjoint processing."""
    event_1 = TaskOutbox(
        id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        task_type="email_send",
        payload={"to": "user1@test.com"},
        priority=1,
        status="pending",
        created_at=datetime.now(timezone.utc),
    )
    event_2 = TaskOutbox(
        id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        task_type="webhook_delivery",
        payload={"url": "https://api.test.com"},
        priority=0,
        status="pending",
        created_at=datetime.now(timezone.utc),
    )

    published_task_ids = []

    async def mock_publish(task_id, task_type, priority=0, traceparent=None):
        published_task_ids.append(task_id)

    # Worker 1 claims event_1, Worker 2 claims event_2
    session_factory_1 = MagicMock()
    db_1 = AsyncMock()
    session_factory_1.return_value.__aenter__.return_value = db_1

    session_factory_2 = MagicMock()
    db_2 = AsyncMock()
    session_factory_2.return_value.__aenter__.return_value = db_2

    with patch("app.outbox.relay.claim_pending_events") as mock_claim, \
         patch("app.outbox.relay.publish_task", side_effect=mock_publish), \
         patch("app.outbox.relay.mark_published", new_callable=AsyncMock) as mock_mark:

        mock_claim.side_effect = [[event_1], [event_2]]

        worker_1 = OutboxRelayService(session_factory=session_factory_1, batch_size=10)
        worker_2 = OutboxRelayService(session_factory=session_factory_2, batch_size=10)

        # Run both workers
        count_1 = await worker_1.run_once()
        count_2 = await worker_2.run_once()

        assert count_1 == 1
        assert count_2 == 1
        assert len(published_task_ids) == 2
        # Ensure zero duplicate publications
        assert str(event_1.task_id) in published_task_ids
        assert str(event_2.task_id) in published_task_ids
        assert len(set(published_task_ids)) == 2
        assert mock_mark.await_count == 2

        # Both sessions committed at batch end
        db_1.commit.assert_awaited_once()
        db_2.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_relay_holds_locks_and_commits_at_batch_end():
    """Verify mark_published is called with commit=False during batch and db.commit is called once."""
    event = TaskOutbox(
        id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        task_type="email_send",
        payload={},
        priority=0,
        status="pending",
        created_at=datetime.now(timezone.utc),
    )

    session_factory = MagicMock()
    db = AsyncMock()
    session_factory.return_value.__aenter__.return_value = db

    with patch("app.outbox.relay.claim_pending_events", AsyncMock(return_value=[event])), \
         patch("app.outbox.relay.publish_task", AsyncMock()), \
         patch("app.outbox.relay.mark_published", new_callable=AsyncMock) as mock_mark:

        service = OutboxRelayService(session_factory=session_factory, batch_size=5)
        drained = await service.run_once()

        assert drained == 1
        # commit=False passed to preserve locks
        mock_mark.assert_awaited_once_with(db, event.id, commit=False)
        db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_mark_published_and_failed_commit_flag():
    """Verify mark_published and mark_failed obey the commit flag."""
    db = AsyncMock()
    event = TaskOutbox(
        id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        task_type="email_send",
        payload={},
        status="pending",
        retry_count=0,
    )
    db.get.return_value = event

    # With commit=False, flushes instead of committing
    await mark_published(db, event.id, commit=False)
    assert event.status == "published"
    db.flush.assert_awaited_once()
    assert not db.commit.called

    # Reset
    db.flush.reset_mock()
    event.status = "pending"

    await mark_failed(db, event.id, error="Broker timeout", commit=False)
    assert event.status == "pending"
    assert event.retry_count == 1
    db.flush.assert_awaited_once()
    assert not db.commit.called
