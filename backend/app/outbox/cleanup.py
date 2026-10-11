"""Retention and cleanup procedures for published outbox records (FEAT-02)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task_outbox import TaskOutbox
from app.outbox.metrics import outbox_pruned_total

logger = logging.getLogger("outbox.cleanup")


async def prune_published_outbox(
    db: AsyncSession,
    retention_hours: int = 24,
) -> int:
    """Delete published outbox records older than retention threshold.
    
    Leaves pending, failed, or fresh published rows completely untouched.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=retention_hours)
    stmt = (
        delete(TaskOutbox)
        .where(
            TaskOutbox.status == "published",
            TaskOutbox.processed_at < cutoff,
        )
    )
    result = await db.execute(stmt)
    await db.commit()
    pruned_count = result.rowcount or 0
    if pruned_count > 0:
        logger.info(
            "Pruned %d published outbox records older than %d hours.",
            pruned_count,
            retention_hours,
        )
        outbox_pruned_total.inc(pruned_count)
    return pruned_count
