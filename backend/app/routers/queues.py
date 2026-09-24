"""Queue metrics router — query RabbitMQ queue depths via management API.

Admin-only endpoint per Phase 8 spec.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter
from sqlalchemy import extract, func, select

from app.core.deps import AdminUser, DBSession
from app.core.rabbitmq import get_queue_depths
from app.models.task import Task

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "",
    summary="Get queue depth metrics",
)
async def get_queues(
    admin: AdminUser,
) -> dict:
    """Return per-queue message depths for all taskforge queues."""
    depths = await get_queue_depths()

    result: dict[str, dict] = {}
    for queue_name, message_count in sorted(depths.items()):
        if "." not in queue_name:
            continue
        parts = queue_name.split(".")
        if len(parts) < 2:
            continue
        task_type = parts[1]
        queue_kind = parts[2] if len(parts) > 2 else "main"

        if task_type not in result:
            result[task_type] = {
                "task_type": task_type,
                "main_depth": 0,
                "retry_depth": 0,
                "dlq_depth": 0,
            }

        if queue_kind == "main" or queue_kind == "tasks":
            result[task_type]["main_depth"] = message_count
        elif queue_kind == "retry":
            result[task_type]["retry_depth"] = message_count
        elif queue_kind == "dlq":
            result[task_type]["dlq_depth"] = message_count

    # Add total depth per type
    for type_data in result.values():
        type_data["total_depth"] = (
            type_data["main_depth"]
            + type_data["retry_depth"]
            + type_data["dlq_depth"]
        )

    return {"queues": list(result.values())}


@router.get(
    "/stats",
    summary="Get aggregate queue/system stats",
)
async def get_stats(
    admin: AdminUser,
    db: DBSession,
) -> dict:
    """Status counts, recent throughput, and latency averages for the dashboard."""
    now = datetime.now(timezone.utc)

    status_rows = await db.execute(
        select(Task.status, func.count()).group_by(Task.status)
    )
    counts = {row[0]: row[1] for row in status_rows.all()}

    async def _completed_per_minute(minutes: int) -> float:
        since = now - timedelta(minutes=minutes)
        result = await db.execute(
            select(func.count()).where(
                Task.completed_at.is_not(None),
                Task.completed_at >= since,
            )
        )
        total = result.scalar_one()
        return round(total / minutes, 2)

    avg_pickup = await db.execute(
        select(
            func.avg(
                extract("epoch", Task.started_at)
                - extract("epoch", Task.created_at)
            )
        ).where(Task.started_at.is_not(None))
    )
    avg_execution = await db.execute(
        select(
            func.avg(
                extract("epoch", Task.completed_at)
                - extract("epoch", Task.started_at)
            )
        ).where(Task.completed_at.is_not(None), Task.started_at.is_not(None))
    )
    pickup = avg_pickup.scalar_one()
    execution = avg_execution.scalar_one()

    return {
        "status_counts": counts,
        "throughput": {
            "tasks_completed_per_minute_5m": await _completed_per_minute(5),
            "tasks_completed_per_minute_60m": await _completed_per_minute(60),
        },
        "latency": {
            "avg_pickup_seconds": None if pickup is None else round(float(pickup), 2),
            "avg_execution_seconds": None if execution is None else round(float(execution), 2),
        },
        "generated_at": now.isoformat(),
    }
