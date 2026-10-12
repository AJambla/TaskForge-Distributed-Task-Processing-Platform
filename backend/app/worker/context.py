"""TaskContext for TaskForge handlers.

Provides handlers with execution metadata and helper APIs for:
- Reporting incremental task progress to Redis Pub/Sub / SSE
- Accessing task identifiers, attempt numbers, and trace contexts
"""
from __future__ import annotations

import json
import logging

from app.core.redis import get_redis

logger = logging.getLogger("worker.context")


class TaskContext:
    """Execution context injected into custom task handlers."""

    def __init__(
        self,
        task_id: str,
        task_type: str,
        attempt: int = 1,
        worker_id: str | None = None,
        trace_id: str | None = None,
    ):
        self.task_id = str(task_id)
        self.task_type = str(task_type)
        self.attempt = int(attempt)
        self.worker_id = str(worker_id) if worker_id else None
        self.trace_id = str(trace_id) if trace_id else None

    async def set_progress(self, percent: int, message: str | None = None) -> None:
        """Publish real-time progress update (0-100%) to Redis SSE event stream."""
        clamped_percent = max(0, min(100, int(percent)))
        payload = {
            "task_id": self.task_id,
            "status": "running",
            "progress": clamped_percent,
            "message": message,
        }
        try:
            redis_client = await get_redis()
            await redis_client.publish(
                f"task:events:{self.task_id}", json.dumps(payload)
            )
        except Exception as exc:
            logger.debug(
                "Failed to publish progress for task %s: %s", self.task_id, exc
            )

    async def is_cancelled(self) -> bool:
        """Check if cancellation has been requested for this running task."""
        try:
            redis_client = await get_redis()
            val = await redis_client.exists(f"task:cancelled:{self.task_id}")
            return val == 1 or val is True
        except Exception as exc:
            logger.debug(
                "Failed to check cancellation flag for task %s: %s", self.task_id, exc
            )
            return False
