"""Transactional Outbox processor and drain utility (IMP-12 / FEAT-02)."""
from __future__ import annotations

import logging
from app.outbox.service import claim_pending_events, mark_published, mark_failed
from app.core.rabbitmq import publish_task

logger = logging.getLogger(__name__)


async def drain_outbox(db, limit: int = 50) -> int:
    """Drain pending outbox rows safely using SKIP LOCKED.

    Returns the count of successfully published rows.
    """
    pending_records = await claim_pending_events(db, batch_size=limit)
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
            await mark_published(db, record.id)
            drained_count += 1
        except Exception as exc:
            await mark_failed(db, record.id, error=str(exc))
            logger.warning(
                "Failed to relay outbox record %s (task %s): %s",
                record.id,
                record.task_id,
                exc,
            )

    return drained_count
