"""TaskForge Scheduler — re-schedules recurring tasks from RabbitMQ.

Uses APScheduler to periodically scan for tasks with recurrence_rule
that are due, and publishes new task messages for the next occurrence.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.core.rabbitmq import RabbitMQPublisher
from app.core.redis import acquire_distributed_lock, close_redis
from app.models.task import Task
from app.models.worker_registration import WorkerRegistration

SETTINGS = get_settings()

logging.basicConfig(
    level=getattr(logging, SETTINGS.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("scheduler")
_SCHEDULER_HOSTNAME: str = os.environ.get(
    "SCHEDULER_HOSTNAME", socket.gethostname()
)
SCAN_INTERVAL_SECONDS = SETTINGS.scheduler_scan_interval_seconds
_HEARTBEAT_INTERVAL_SECONDS = 15
_LOCK_TTL_SECONDS = 10

_scheduler_engine = create_async_engine(
    SETTINGS.database_url,
    pool_size=2,
    max_overflow=4,
    pool_pre_ping=True,
    echo=SETTINGS.app_env == "development",
)
SchedulerSessionLocal = async_sessionmaker(
    _scheduler_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


def _next_occurrence(run_at: datetime, recurrence_rule: str) -> datetime | None:
    """Compute the next run_at from a cron recurrence rule."""
    try:
        from croniter import croniter
        base = run_at.replace(tzinfo=timezone.utc)
        return croniter(recurrence_rule, base).get_next(datetime)
    except Exception:
        logger.warning("Failed to compute next occurrence for recurrence rule %r", recurrence_rule)
        return None


async def _reschedule_recurring_tasks() -> int:
    """Scan for due recurring tasks and publish new ones.

    Returns the number of tasks re-scheduled.
    """
    reScheduled = 0
    try:
        async with SchedulerSessionLocal() as db:
            result = await db.execute(
                select(Task)
                .where(
                    Task.recurrence_rule.isnot(None),
                    Task.status == "queued",
                    Task.run_at <= datetime.now(timezone.utc),
                )
                .order_by(Task.run_at.asc())
                .limit(100)
            )
            tasks = result.scalars().all()

        publisher = RabbitMQPublisher()
        await publisher.connect()

        for task in tasks:
            lock_acquired = False
            try:
                lock_acquired = await acquire_distributed_lock(
                    f"scheduler:{task.id}",
                    _SCHEDULER_HOSTNAME,
                    ttl_seconds=_LOCK_TTL_SECONDS,
                )
                if not lock_acquired:
                    logger.debug(
                        "Skipping task %s — lock held by another scheduler instance.",
                        task.id,
                    )
                    continue

                next_run_at = _next_occurrence(task.run_at, task.recurrence_rule)
                if next_run_at is None:
                    logger.warning(
                        "Could not parse recurrence_rule for task %s: %r",
                        task.id,
                        task.recurrence_rule,
                    )
                    continue

                new_task = Task(
                    user_id=task.user_id,
                    task_type=task.task_type,
                    payload=task.payload,
                    status="queued",
                    priority=task.priority,
                    max_attempts=task.max_attempts,
                    run_at=next_run_at,
                    recurrence_rule=task.recurrence_rule,
                    schedule_id=task.schedule_id,
                )
                async with SchedulerSessionLocal() as new_db:
                    # Clear recurrence_rule on the current task so it does not trigger duplicate re-scheduling
                    current_task = await new_db.get(Task, task.id)
                    if current_task is not None:
                        current_task.recurrence_rule = None

                    # If linked to a parent schedule, update its last/next run metadata
                    if task.schedule_id:
                        from app.models.schedule import Schedule
                        parent_schedule = await new_db.get(Schedule, task.schedule_id)
                        if parent_schedule:
                            parent_schedule.last_run_at = datetime.now(timezone.utc)
                            parent_schedule.next_run_at = next_run_at

                    new_db.add(new_task)
                    await new_db.commit()
                    # Publish the currently due task execution
                    await publisher.publish(str(task.id), task.task_type)
                reScheduled += 1
                logger.info(
                    "Re-scheduled task %s (published current, cloned new task %s for next run_at=%s, schedule=%s)",
                    task.id,
                    new_task.id,
                    next_run_at,
                    task.schedule_id,
                )

            except Exception:
                logger.exception("Error rescheduling task %s", task.id)

        await publisher.close()

    except Exception:
        logger.exception("Error in reschedule scan")

    return reScheduled


async def _register_scheduler(db) -> WorkerRegistration:
    # Reclaim stale 'online' rows from previous (possibly killed) runs so
    # restarts don't accumulate phantom registrations for this hostname.
    await db.execute(
        update(WorkerRegistration)
        .where(
            WorkerRegistration.hostname == _SCHEDULER_HOSTNAME,
            WorkerRegistration.status == "online",
        )
        .values(status="offline")
    )
    worker = WorkerRegistration(
        hostname=_SCHEDULER_HOSTNAME,
        status="online",
        concurrency_limit=1,
    )
    db.add(worker)
    # commit (not just flush) so the row survives the session close.
    await db.commit()
    await db.refresh(worker)
    logger.info(
        "Scheduler registered: id=%s hostname=%s", worker.id, worker.hostname
    )
    return worker


async def _update_heartbeat(db, worker: WorkerRegistration) -> None:
    await db.execute(
        update(WorkerRegistration)
        .where(WorkerRegistration.id == worker.id)
        .values(last_heartbeat_at=datetime.now(timezone.utc))
    )
    await db.commit()


async def _heartbeat_loop(worker: WorkerRegistration) -> None:
    while True:
        await asyncio.sleep(_HEARTBEAT_INTERVAL_SECONDS)
        try:
            async with SchedulerSessionLocal() as db:
                await _update_heartbeat(db, worker)
        except Exception:
            logger.exception("Heartbeat update failed for scheduler %s", worker.id)


async def _mark_scheduler_offline(db, worker_id) -> None:
    await db.execute(
        update(WorkerRegistration)
        .where(WorkerRegistration.id == worker_id)
        .values(status="offline")
    )
    await db.commit()
    logger.info("Scheduler marked offline: id=%s", worker_id)


async def prune_stale_workers(db: AsyncSession | None = None) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(
        seconds=SETTINGS.worker_heartbeat_timeout_seconds
    )
    stmt = (
        update(WorkerRegistration)
        .where(
            WorkerRegistration.status == "online",
            WorkerRegistration.last_heartbeat_at < cutoff,
        )
        .values(
            status="offline",
            last_heartbeat_at=WorkerRegistration.last_heartbeat_at,
        )
    )
    if db is not None:
        result = await db.execute(stmt)
        await db.commit()
        pruned_count = result.rowcount
    else:
        async with SchedulerSessionLocal() as session:
            result = await session.execute(stmt)
            await session.commit()
            pruned_count = result.rowcount

    if pruned_count > 0:
        try:
            from app.worker.metrics import worker_heartbeat_missed_total
            worker_heartbeat_missed_total.inc(pruned_count)
        except Exception:
            pass

    return pruned_count


async def main() -> None:
    logger.info("Starting TaskForge scheduler (hostname=%s)...", _SCHEDULER_HOSTNAME)

    publisher = RabbitMQPublisher()
    await publisher.connect()
    worker = None
    heartbeat_task = None
    shutdown_event = asyncio.Event()

    try:
        async with SchedulerSessionLocal() as db:
            worker = await _register_scheduler(db)

        heartbeat_task = asyncio.create_task(_heartbeat_loop(worker))

        loop = asyncio.get_running_loop()

        def _handle_signal() -> None:
            shutdown_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _handle_signal)
            except NotImplementedError:
                pass

        logger.info(
            "Scheduler ready. Scanning every %ds...", SCAN_INTERVAL_SECONDS
        )
        while not shutdown_event.is_set():
            is_leader = await acquire_distributed_lock(
                "lock:scheduler:scan",
                _SCHEDULER_HOSTNAME,
                ttl_seconds=max(5, SCAN_INTERVAL_SECONDS - 2),
            )
            if is_leader:
                try:
                    count = await _reschedule_recurring_tasks()
                    if count > 0:
                        logger.info("Rescheduled %d recurring task(s).", count)
                except Exception:
                    logger.exception("Error in reschedule loop")
                try:
                    pruned = await prune_stale_workers()
                    if pruned > 0:
                        logger.info("Pruned %d stale worker(s) to offline.", pruned)
                except Exception:
                    logger.exception("Error in prune_stale_workers")
            else:
                logger.debug("Another scheduler instance is currently the active scan leader.")

            try:
                await asyncio.wait_for(
                    shutdown_event.wait(), timeout=SCAN_INTERVAL_SECONDS
                )
            except asyncio.TimeoutError:
                pass

    except Exception:
        logger.exception("Unexpected error in scheduler main loop")
    finally:
        if heartbeat_task:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

        if worker is not None:
            try:
                async with SchedulerSessionLocal() as db:
                    await _mark_scheduler_offline(db, worker.id)
            except Exception:
                logger.exception("Failed to mark scheduler offline")

        await publisher.close()
        await _scheduler_engine.dispose()
        await close_redis()
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    asyncio.run(main())
