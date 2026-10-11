"""Database operations and queries for Transactional Outbox (FEAT-02)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task_outbox import TaskOutbox
from app.outbox.metrics import (
    outbox_messages_relayed_total,
    outbox_relay_errors_total,
    outbox_retry_total,
)

logger = logging.getLogger("outbox.service")


def calculate_backoff_seconds(retry_count: int, max_backoff: int = 300) -> int:
    """Calculate exponential backoff delay in seconds."""
    return min(max_backoff, 2 ** retry_count)


async def create_outbox_event(
    db: AsyncSession,
    task_id: UUID,
    task_type: str,
    payload: dict,
    priority: int = 0,
    event_type: str = "task_created",
    traceparent: str | None = None,
) -> TaskOutbox:
    """Insert a new pending outbox event inside the active SQL transaction."""
    event = TaskOutbox(
        task_id=task_id,
        task_type=task_type,
        payload=payload,
        priority=priority,
        event_type=event_type,
        traceparent=traceparent,
        status="pending",
        retry_count=0,
        next_attempt_at=datetime.now(timezone.utc),
    )
    db.add(event)
    return event


async def claim_pending_events(
    db: AsyncSession,
    batch_size: int = 100,
) -> list[TaskOutbox]:
    """Atomically claim pending events eligible for dispatch using SKIP LOCKED."""
    now = datetime.now(timezone.utc)
    stmt = (
        select(TaskOutbox)
        .where(
            TaskOutbox.status == "pending",
            TaskOutbox.next_attempt_at <= now,
        )
        .order_by(TaskOutbox.created_at.asc())
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def mark_published(db: AsyncSession, event_id: UUID) -> None:
    """Mark an outbox event as successfully published."""
    event = await db.get(TaskOutbox, event_id)
    if not event:
        return
    now = datetime.now(timezone.utc)
    event.status = "published"
    event.processed_at = now
    await db.commit()
    outbox_messages_relayed_total.labels(task_type=event.task_type).inc()


async def mark_failed(
    db: AsyncSession,
    event_id: UUID,
    error: str,
    max_retries: int = 10,
) -> None:
    """Record a failure and schedule next exponential backoff attempt."""
    event = await db.get(TaskOutbox, event_id)
    if not event:
        return
    now = datetime.now(timezone.utc)
    event.retry_count += 1
    event.last_attempt_at = now
    event.last_error = str(error)

    if event.retry_count >= max_retries:
        event.status = "failed"
        logger.error(
            "Outbox event %s (task %s) permanently failed after %d retries: %s",
            event.id,
            event.task_id,
            event.retry_count,
            error,
        )
    else:
        delay = calculate_backoff_seconds(event.retry_count - 1)
        event.next_attempt_at = now + timedelta(seconds=delay)
        event.status = "pending"
        logger.warning(
            "Outbox event %s failed (attempt %d). Retrying in %ds: %s",
            event.id,
            event.retry_count,
            delay,
            error,
        )
        outbox_retry_total.labels(task_type=event.task_type).inc()

    await db.commit()
    outbox_relay_errors_total.labels(task_type=event.task_type).inc()
