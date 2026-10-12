"""Queue metrics router — query RabbitMQ queue depths via management API.

Read endpoints are available to any authenticated user: queue backlog is
shared platform visibility.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter
from sqlalchemy import extract, func, select

from app.core.deps import AdminUser, CurrentUser, DBSession
from app.core.rabbitmq import get_queue_depths, publish_task, purge_queue
from app.models.task import Task

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "",
    summary="Get queue depth metrics",
)
async def get_queues(
    current_user: CurrentUser,
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
            result[task_type]["main_depth"] += message_count
        elif queue_kind.startswith("retry"):
            result[task_type]["retry_depth"] += message_count
        elif queue_kind == "dlq":
            result[task_type]["dlq_depth"] += message_count

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
    current_user: CurrentUser,
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


@router.get(
    "/dlq",
    summary="Inspect dead-letter queues",
)
async def inspect_dlq(
    current_user: CurrentUser,
    db: DBSession,
) -> dict:
    """Return depths and recent dead-letter tasks."""
    depths = await get_queue_depths()
    dlq_depths = {k: v for k, v in depths.items() if k.endswith(".dlq")}

    result = await db.execute(
        select(Task)
        .where(Task.status == "dead_letter")
        .order_by(Task.completed_at.desc())
        .limit(50)
    )
    dead_tasks = result.scalars().all()

    return {
        "dlq_depths": dlq_depths,
        "dead_letter_count": len(dead_tasks),
        "recent_dead_tasks": [
            {
                "id": str(t.id),
                "task_type": t.task_type,
                "attempt_count": t.attempt_count,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            }
            for t in dead_tasks
        ],
    }


@router.post(
    "/dlq/redrive",
    summary="Redrive dead-letter tasks back to main queue",
)
async def redrive_dlq(
    current_user: AdminUser,
    db: DBSession,
    task_type: str | None = None,
    limit: int = 100,
) -> dict:
    """Re-queue dead-letter tasks into the main processing queue."""
    query = select(Task).where(Task.status == "dead_letter")
    if task_type:
        query = query.where(Task.task_type == task_type)
    query = query.order_by(Task.completed_at.asc()).limit(min(limit, 500))

    result = await db.execute(query)
    tasks = result.scalars().all()

    redriven_ids = []
    types_redriven = set()
    for task in tasks:
        task.status = "queued"
        task.attempt_count = 0
        task.started_at = None
        task.completed_at = None
        task.run_at = datetime.now(timezone.utc)
        await publish_task(str(task.id), task.task_type)
        redriven_ids.append(str(task.id))
        types_redriven.add(task.task_type)

    await db.commit()

    # Drain messages from RabbitMQ DLQs so the broker queue doesn't remain cluttered (IMP-10)
    for t_type in types_redriven:
        dlq_name = f"tasks.{t_type}.dlq"
        await purge_queue(dlq_name)

    logger.info("Redrove %d dead-letter tasks back to queues.", len(redriven_ids))
    return {
        "redriven_count": len(redriven_ids),
        "task_ids": redriven_ids,
    }

