"""Queue metrics router — query RabbitMQ queue depths via management API.

Admin-only endpoint per Phase 8 spec.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.core.deps import AdminUser
from app.core.rabbitmq import get_queue_depths

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
