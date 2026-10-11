"""Unit tests for Schedule model and scheduler linkage (IMP-13)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
from datetime import datetime, timezone, timedelta

from app.models.task import Task
from app.models.schedule import Schedule
from app.scheduler import main as scheduler_main


@pytest.mark.asyncio
async def test_schedule_model_attributes():
    sched_id = uuid.uuid4()
    user_id = uuid.uuid4()
    sched = Schedule(
        id=sched_id,
        user_id=user_id,
        name="Daily Email Digest",
        task_type="email_send",
        payload={"to": "digest@example.com", "subject": "Digest", "body": "Summary"},
        recurrence_rule="0 9 * * *",
        timezone="America/New_York",
        is_paused=False,
    )
    assert sched.id == sched_id
    assert sched.timezone == "America/New_York"
    assert sched.is_paused is False


@pytest.mark.asyncio
async def test_scheduler_updates_parent_schedule_metadata():
    sched_id = uuid.uuid4()
    parent_sched = Schedule(
        id=sched_id,
        user_id=uuid.uuid4(),
        task_type="email_send",
        payload={},
        recurrence_rule="*/5 * * * *",
    )
    due_task = Task(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        task_type="email_send",
        payload={},
        status="queued",
        priority=0,
        run_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        recurrence_rule="*/5 * * * *",
        schedule_id=sched_id,
    )

    mock_db = AsyncMock()
    mock_db.execute.return_value = MagicMock(scalars=lambda: MagicMock(all=lambda: [due_task]))

    mock_new_db = AsyncMock()
    mock_new_db.get.side_effect = lambda model, obj_id: due_task if model is Task else parent_sched
    mock_new_db.add = MagicMock()
    mock_new_db.commit = AsyncMock()

    mock_publisher = AsyncMock()

    mock_session_maker = MagicMock()
    mock_session_maker.side_effect = [
        # First call for initial query db
        MagicMock(__aenter__=AsyncMock(return_value=mock_db), __aexit__=AsyncMock(return_value=False)),
        # Second call for new_db updates
        MagicMock(__aenter__=AsyncMock(return_value=mock_new_db), __aexit__=AsyncMock(return_value=False)),
    ]

    with patch("app.scheduler.main.SchedulerSessionLocal", mock_session_maker), \
         patch("app.scheduler.main.acquire_distributed_lock", return_value=True), \
         patch("app.scheduler.main.RabbitMQPublisher", return_value=mock_publisher):

        count = await scheduler_main._reschedule_recurring_tasks()

        assert count == 1
        assert parent_sched.last_run_at is not None
        assert parent_sched.next_run_at is not None
        assert mock_new_db.commit.called
