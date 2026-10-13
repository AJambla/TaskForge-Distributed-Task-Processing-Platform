"""Worker lifecycle management: registration, heartbeats, status updates, and draining (IMP-21)."""
from __future__ import annotations

import json
import logging
import os
import socket
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any


from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.task import Task
from app.models.task_attempt import TaskAttempt
from app.models.worker_registration import WorkerRegistration
from app.worker.metrics import (
    worker_active_tasks,
    worker_concurrency_limit,
    worker_utilization_ratio,
    workers_online_total,
)

logger = logging.getLogger("worker.lifecycle")
_SETTINGS = get_settings()
_WORKER_HOSTNAME: str = os.environ.get("WORKER_HOSTNAME", socket.gethostname())
_HEARTBEAT_INTERVAL_SECONDS = 15


async def create_attempt(
    db: AsyncSession, task: Task, worker_id=None, trace_id: str | None = None
) -> TaskAttempt:
    """Record a new task attempt in PostgreSQL."""
    resolved_trace_id = trace_id or getattr(task, "trace_id", None)
    attempt = TaskAttempt(
        task_id=task.id,
        attempt_number=task.attempt_count,
        worker_id=worker_id,
        started_at=datetime.now(timezone.utc),
        trace_id=resolved_trace_id,
    )
    db.add(attempt)
    await db.flush()
    return attempt


async def update_worker_stats(
    db: AsyncSession,
    worker_id,
    tasks_processed: int = 0,
    tasks_failed: int = 0,
) -> None:
    """Increment worker processed/failed counters in database."""
    if worker_id is None:
        return
    await db.execute(
        update(WorkerRegistration)
        .where(WorkerRegistration.id == worker_id)
        .values(
            tasks_processed=WorkerRegistration.tasks_processed + tasks_processed,
            tasks_failed=WorkerRegistration.tasks_failed + tasks_failed,
        )
    )
    await db.commit()


async def mark_success(
    db: AsyncSession,
    task: Task,
    attempt: TaskAttempt,
    worker_id=None,
    result=None,
) -> None:
    """Transition task and attempt to succeeded state and publish SSE event."""
    if task.status == "cancelled":
        attempt.outcome = "failure"
        attempt.finished_at = datetime.now(timezone.utc)
        attempt.error_message = "Task execution aborted due to cancellation"
        await db.commit()
        return

    task.status = "succeeded"
    task.completed_at = datetime.now(timezone.utc)
    if isinstance(result, dict):
        task.result = result
        attempt.result = result
    attempt.outcome = "success"
    attempt.finished_at = datetime.now(timezone.utc)
    attempt.error_message = None
    attempt.error_detail = None
    await db.commit()
    await update_worker_stats(db, worker_id, tasks_processed=1)

    # Publish SSE event via Redis Pub/Sub (IMP-19)
    try:
        from app.core.redis import get_redis
        redis_client = await get_redis()
        event_payload = json.dumps({
            "task_id": str(task.id),
            "status": task.status,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "result": task.result,
        })
        await redis_client.publish(f"task:events:{task.id}", event_payload)
    except Exception as exc:
        logger.debug("Failed to publish SSE event for task %s: %s", task.id, exc)


async def mark_failure(
    db: AsyncSession,
    task: Task,
    attempt: TaskAttempt,
    outcome: str,
    exc: Exception | None = None,
    worker_id=None,
    error_message: str | None = None,
    error_detail: dict | None = None,
) -> None:
    """Transition attempt to failed/timeout state and task to retrying or failed."""
    attempt.outcome = outcome
    attempt.finished_at = datetime.now(timezone.utc)
    if error_message is not None:
        attempt.error_message = error_message
    elif exc is not None:
        attempt.error_message = str(exc) if str(exc) else exc.__class__.__name__

    if error_detail is not None:
        attempt.error_detail = error_detail
    elif exc is not None:
        attempt.error_detail = {"traceback": traceback.format_exc(), "error_type": exc.__class__.__name__}

    if task.attempt_count < task.max_attempts:
        task.status = "retrying"
    else:
        task.status = "failed"
    await db.commit()
    if outcome in ("failure", "timeout"):
        await update_worker_stats(db, worker_id, tasks_failed=1)

    # Publish SSE event via Redis Pub/Sub (IMP-19)
    try:
        from app.core.redis import get_redis
        redis_client = await get_redis()
        event_payload = json.dumps({
            "task_id": str(task.id),
            "status": task.status,
            "error_message": attempt.error_message,
        })
        await redis_client.publish(f"task:events:{task.id}", event_payload)
    except Exception as redis_exc:
        logger.debug("Failed to publish SSE event for task %s: %s", task.id, redis_exc)


async def register_worker(db: AsyncSession) -> WorkerRegistration:
    """Register this worker instance online in the database."""
    instance_name = f"{_WORKER_HOSTNAME}:{os.getpid()}"
    await db.execute(
        update(WorkerRegistration)
        .where(
            WorkerRegistration.hostname == instance_name,
            WorkerRegistration.status == "online",
        )
        .values(status="offline")
    )
    # Prune stale offline registrations older than 24 hours to prevent unbounded table growth
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    await db.execute(
        delete(WorkerRegistration)
        .where(
            WorkerRegistration.status == "offline",
            WorkerRegistration.last_heartbeat_at < cutoff,
        )
    )
    worker = WorkerRegistration(
        hostname=instance_name,
        status="online",
        concurrency_limit=_SETTINGS.worker_concurrency,
    )
    db.add(worker)
    await db.commit()
    await db.refresh(worker)
    logger.info("Worker registered: id=%s hostname=%s", worker.id, worker.hostname)
    workers_online_total.set(1)
    worker_concurrency_limit.set(_SETTINGS.worker_concurrency)
    return worker


async def update_heartbeat(
    db: AsyncSession,
    worker: WorkerRegistration,
    active_count: int = 0,
    concurrency_limit: int | None = None,
) -> dict[str, Any]:
    """Persist worker heartbeat timestamp, current task count, and capacity metrics."""
    limit = (
        concurrency_limit
        or getattr(worker, "concurrency_limit", None)
        or _SETTINGS.worker_concurrency
    )
    utilization_rate = round(active_count / max(1, limit), 4)

    values = {
        "last_heartbeat_at": datetime.now(timezone.utc),
        "current_task_count": active_count,
    }
    if concurrency_limit is not None:
        values["concurrency_limit"] = concurrency_limit

    await db.execute(
        update(WorkerRegistration)
        .where(WorkerRegistration.id == worker.id)
        .values(**values)
    )
    await db.commit()

    # Update Prometheus gauges
    worker_active_tasks.set(active_count)
    worker_concurrency_limit.set(limit)
    worker_utilization_ratio.set(utilization_rate)

    # Persist live capacity snapshot in Redis for dashboards
    try:
        from app.core.redis import get_redis
        redis_client = await get_redis()
        heartbeat_data = json.dumps({
            "worker_id": str(worker.id),
            "hostname": getattr(worker, "hostname", "unknown"),
            "active_task_count": active_count,
            "concurrency_limit": limit,
            "utilization_rate": utilization_rate,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        await redis_client.set(f"worker:heartbeat:{worker.id}", heartbeat_data, ex=30)
    except Exception as exc:
        logger.debug("Failed to publish worker heartbeat to Redis: %s", exc)

    return {
        "active_task_count": active_count,
        "concurrency_limit": limit,
        "utilization_rate": utilization_rate,
    }


async def set_worker_offline(db: AsyncSession, worker_id) -> None:
    """Mark worker registration offline on graceful termination."""
    await db.execute(
        update(WorkerRegistration)
        .where(WorkerRegistration.id == worker_id)
        .values(status="offline")
    )
    await db.commit()
    logger.info("Worker marked offline: id=%s", worker_id)
    workers_online_total.set(0)
    worker_active_tasks.set(0)
    worker_utilization_ratio.set(0.0)

