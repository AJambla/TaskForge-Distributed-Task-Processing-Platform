"""Automated worker crash detection and stale task reclamation (Phase 3)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.task import Task
from app.models.task_attempt import TaskAttempt
from app.models.task_outbox import TaskOutbox
from app.models.worker_registration import WorkerRegistration

logger = logging.getLogger("core.recovery")


class RecoveryStats(NamedTuple):
    dead_workers: int
    recovered_tasks: int
    dead_lettered_tasks: int


async def recover_stale_tasks(
    db: AsyncSession,
    stale_threshold_seconds: int = 45,
) -> RecoveryStats:
    """Scan for online workers with expired heartbeats, mark them offline,
    close their abandoned task attempts, and re-queue or dead-letter their tasks.

    Returns:
        RecoveryStats(dead_workers, recovered_tasks, dead_lettered_tasks)
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=stale_threshold_seconds)

    # 1. Identify workers whose heartbeats have timed out
    result = await db.execute(
        select(WorkerRegistration).where(
            WorkerRegistration.status == "online",
            WorkerRegistration.last_heartbeat_at < cutoff,
        )
    )
    dead_workers = list(result.scalars().all())
    if not dead_workers:
        return RecoveryStats(dead_workers=0, recovered_tasks=0, dead_lettered_tasks=0)

    dead_worker_ids = [w.id for w in dead_workers]
    dead_worker_hostnames = {w.id: w.hostname for w in dead_workers}

    # 2. Mark dead workers as offline
    for worker in dead_workers:
        worker.status = "offline"
        logger.warning(
            "Worker %s (hostname=%s) missed heartbeats (last seen %s) — marked offline.",
            worker.id,
            worker.hostname,
            worker.last_heartbeat_at.isoformat() if worker.last_heartbeat_at else "never",
        )

    # 3. Find all tasks with open attempts on those dead workers
    stmt = (
        select(Task)
        .where(
            Task.status.in_(["running", "queued", "retrying"]),
            Task.id.in_(
                select(TaskAttempt.task_id).where(
                    TaskAttempt.worker_id.in_(dead_worker_ids),
                    TaskAttempt.finished_at.is_(None),
                )
            ),
        )
        .options(selectinload(Task.attempts))
        .with_for_update(skip_locked=True)
    )
    task_res = await db.execute(stmt)
    stale_tasks = list(task_res.scalars().all())

    recovered_count = 0
    dead_letter_count = 0

    for task in stale_tasks:
        # Close open attempts associated with dead workers
        for attempt in task.attempts:
            if attempt.worker_id in dead_worker_ids and attempt.finished_at is None:
                attempt.outcome = "failure"
                attempt.finished_at = now
                attempt.error_message = (
                    f"Worker heartbeat lost (crash detected on {dead_worker_hostnames.get(attempt.worker_id, 'unknown')})"
                )
                attempt.error_detail = {
                    "reason": "worker_crash_detected",
                    "worker_id": str(attempt.worker_id),
                    "recovered_at": now.isoformat(),
                }

        # Decide whether to re-queue or dead-letter
        if task.attempt_count < task.max_attempts:
            task.status = "queued"
            task.run_at = now
            # Create outbox event to re-publish task for healthy workers
            outbox_entry = TaskOutbox(
                task_id=task.id,
                task_type=task.task_type,
                payload=task.payload,
                priority=task.priority,
                status="pending",
                event_type="task_requeued",
                next_attempt_at=now,
            )
            db.add(outbox_entry)
            recovered_count += 1
            logger.info(
                "Recovered abandoned task %s (attempt %d/%d) — re-queued via outbox.",
                task.id,
                task.attempt_count,
                task.max_attempts,
            )
        else:
            task.status = "dead_letter"
            task.completed_at = now
            dead_letter_count += 1
            logger.warning(
                "Task %s reached max attempts (%d/%d) after worker crash — moved to dead_letter.",
                task.id,
                task.attempt_count,
                task.max_attempts,
            )

    await db.commit()

    return RecoveryStats(
        dead_workers=len(dead_workers),
        recovered_tasks=recovered_count,
        dead_lettered_tasks=dead_letter_count,
    )
