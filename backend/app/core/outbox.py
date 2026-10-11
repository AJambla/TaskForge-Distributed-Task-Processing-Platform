"""Transactional Outbox processor and drain utility (IMP-12)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select, update
from app.models.task_outbox import TaskOutbox
from app.core.rabbitmq import publish_task

logger = logging.getLogger(__name__)


async def drain_outbox(db, limit: int = 50) -> int:
    """Drain pending outbox rows by publishing them to RabbitMQ.

    Returns the count of successfully published rows.
    """
    result = await db.execute(
        select(TaskOutbox)
        .where(TaskOutbox.status == "pending")
        .order_by(TaskOutbox.created_at.asc())
        .limit(limit)
    )
    pending_records = result.scalars().all()
    if not pending_records:
        return 0

    drained_count = 0
    for record in pending_records:
        try:
            await publish_task(
                task_id=str(record.task_id),
                task_type=record.task_type,
                priority=record.priority,
            )
            record.status = "published"
            record.processed_at = datetime.now(timezone.utc)
            drained_count += 1
        except Exception as exc:
            record.retry_count += 1
            if record.retry_count >= 10:
                record.status = "failed"
            logger.warning(
                "Failed to relay outbox record %s (task %s): %s",
                record.id,
                record.task_id,
                exc,
            )

    await db.commit()
    return drained_count
