"""Unit tests for worker crash detection and task recovery (Phase 3)."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
import uuid
import pytest

from app.core.recovery import recover_stale_tasks, RecoveryStats
from app.models.task import Task
from app.models.task_attempt import TaskAttempt
from app.models.task_outbox import TaskOutbox
from app.models.worker_registration import WorkerRegistration


@pytest.mark.asyncio
async def test_recover_stale_tasks_healthy_worker_noop():
    """Verify that healthy workers with recent heartbeats are untouched."""
    db = AsyncMock()
    # No dead workers found
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    db.execute.return_value = mock_result

    stats = await recover_stale_tasks(db, stale_threshold_seconds=45)

    assert stats == RecoveryStats(dead_workers=0, recovered_tasks=0, dead_lettered_tasks=0)
    assert not db.commit.called


@pytest.mark.asyncio
async def test_recover_stale_tasks_requeues_abandoned_task():
    """Verify dead worker is marked offline, attempt closed, and task re-queued via outbox."""
    db = AsyncMock()
    now = datetime.now(timezone.utc)
    expired_heartbeat = now - timedelta(seconds=60)

    dead_worker_id = uuid.uuid4()
    dead_worker = WorkerRegistration(
        id=dead_worker_id,
        hostname="worker-crashed-1",
        status="online",
        concurrency_limit=4,
        last_heartbeat_at=expired_heartbeat,
    )

    task_id = uuid.uuid4()
    abandoned_attempt = TaskAttempt(
        id=uuid.uuid4(),
        task_id=task_id,
        attempt_number=1,
        worker_id=dead_worker_id,
        started_at=expired_heartbeat,
        finished_at=None,
        outcome=None,
    )

    task = Task(
        id=task_id,
        user_id=uuid.uuid4(),
        task_type="email_send",
        payload={"to": "dev@test.com"},
        status="running",
        priority=2,
        max_attempts=3,
        attempt_count=1,
        created_at=expired_heartbeat,
        attempts=[abandoned_attempt],
    )

    # First execute: find dead workers; Second execute: find abandoned tasks
    mock_workers_res = MagicMock()
    mock_workers_res.scalars.return_value.all.return_value = [dead_worker]

    mock_tasks_res = MagicMock()
    mock_tasks_res.scalars.return_value.all.return_value = [task]

    db.execute.side_effect = [mock_workers_res, mock_tasks_res]

    added_objects = []
    db.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))

    stats = await recover_stale_tasks(db, stale_threshold_seconds=45)

    assert stats.dead_workers == 1
    assert stats.recovered_tasks == 1
    assert stats.dead_lettered_tasks == 0

    # Worker transitioned
    assert dead_worker.status == "offline"

    # Attempt closed as failure with diagnostic message
    assert abandoned_attempt.outcome == "failure"
    assert abandoned_attempt.finished_at is not None
    assert "Worker heartbeat lost" in abandoned_attempt.error_message
    assert abandoned_attempt.error_detail["reason"] == "worker_crash_detected"

    # Task re-queued
    assert task.status == "queued"
    assert task.run_at is not None

    # Outbox event created for redelivery
    assert len(added_objects) == 1
    outbox_event = added_objects[0]
    assert isinstance(outbox_event, TaskOutbox)
    assert outbox_event.task_id == task_id
    assert outbox_event.task_type == "email_send"
    assert outbox_event.event_type == "task_requeued"
    assert outbox_event.status == "pending"

    assert db.commit.called


@pytest.mark.asyncio
async def test_recover_stale_tasks_dead_letters_exceeded_attempts():
    """Verify task is routed to dead_letter when attempt_count >= max_attempts."""
    db = AsyncMock()
    now = datetime.now(timezone.utc)
    expired_heartbeat = now - timedelta(seconds=90)

    dead_worker_id = uuid.uuid4()
    dead_worker = WorkerRegistration(
        id=dead_worker_id,
        hostname="worker-crashed-max",
        status="online",
        concurrency_limit=2,
        last_heartbeat_at=expired_heartbeat,
    )

    task_id = uuid.uuid4()
    abandoned_attempt = TaskAttempt(
        id=uuid.uuid4(),
        task_id=task_id,
        attempt_number=3,
        worker_id=dead_worker_id,
        started_at=expired_heartbeat,
        finished_at=None,
        outcome=None,
    )

    task = Task(
        id=task_id,
        user_id=uuid.uuid4(),
        task_type="webhook_delivery",
        payload={"url": "https://api.test.com"},
        status="running",
        priority=0,
        max_attempts=3,
        attempt_count=3,  # Already at max attempts!
        created_at=expired_heartbeat,
        attempts=[abandoned_attempt],
    )

    mock_workers_res = MagicMock()
    mock_workers_res.scalars.return_value.all.return_value = [dead_worker]

    mock_tasks_res = MagicMock()
    mock_tasks_res.scalars.return_value.all.return_value = [task]

    db.execute.side_effect = [mock_workers_res, mock_tasks_res]

    added_objects = []
    db.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))

    stats = await recover_stale_tasks(db, stale_threshold_seconds=45)

    assert stats.dead_workers == 1
    assert stats.recovered_tasks == 0
    assert stats.dead_lettered_tasks == 1

    # Worker offline
    assert dead_worker.status == "offline"

    # Attempt closed
    assert abandoned_attempt.outcome == "failure"
    assert abandoned_attempt.finished_at is not None

    # Task moved to dead_letter
    assert task.status == "dead_letter"
    assert task.completed_at is not None

    # No new outbox event added
    assert len(added_objects) == 0
    assert db.commit.called
