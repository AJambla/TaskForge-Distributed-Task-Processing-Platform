"""Worker lifecycle management: registration, heartbeats, status updates, and draining (IMP-21)."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import traceback
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.task import Task
from app.models.task_attempt import TaskAttempt
from app.models.worker_registration import WorkerRegistration
from app.worker.metrics import workers_online_total

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
    task.status = "succeeded"
    task.completed_at = datetime.now(timezone.utc)
    if isinstance(result, dict):
        task.result = result
        attempt.result = result
        # Persist produced artifacts (FEAT-01)
        raw_artifacts = result.get("artifacts")
        if isinstance(raw_artifacts, list):
            from app.models.artifact import Artifact
            for art in raw_artifacts:
                if isinstance(art, dict) and "storage_key" in art and "filename" in art:
                    db.add(
                        Artifact(
                            task_id=task.id,
                            storage_key=art["storage_key"],
                            filename=art["filename"],
                            content_type=art.get("content_type", "application/octet-stream"),
                            size_bytes=int(art.get("size_bytes", 0)),
                        )
                    )
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
) -> None:
    """Transition attempt to failed/timeout state and task to retrying or failed."""
    attempt.outcome = outcome
    attempt.finished_at = datetime.now(timezone.utc)
    if exc is not None:
        attempt.error_message = str(exc)
        attempt.error_detail = {"traceback": traceback.format_exc()}
    if task.attempt_count < task.max_attempts:
        task.status = "retrying"
    else:
        task.status = "failed"
    await db.commit()
    if outcome == "failure":
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
    await db.execute(
        update(WorkerRegistration)
        .where(
            WorkerRegistration.hostname == _WORKER_HOSTNAME,
            WorkerRegistration.status == "online",
        )
        .values(status="offline")
    )
    worker = WorkerRegistration(
        hostname=_WORKER_HOSTNAME,
        status="online",
        concurrency_limit=_SETTINGS.worker_concurrency,
    )
    db.add(worker)
    await db.commit()
    await db.refresh(worker)
    logger.info("Worker registered: id=%s hostname=%s", worker.id, worker.hostname)
    workers_online_total.set(1)
    return worker


async def update_heartbeat(db: AsyncSession, worker: WorkerRegistration, active_count: int = 0) -> None:
    """Persist worker heartbeat timestamp and current task load."""
    await db.execute(
        update(WorkerRegistration)
        .where(WorkerRegistration.id == worker.id)
        .values(
            last_heartbeat_at=datetime.now(timezone.utc),
            current_task_count=active_count,
        )
    )
    await db.commit()


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
