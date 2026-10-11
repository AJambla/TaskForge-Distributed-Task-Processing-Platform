"""TaskContext for TaskForge pluggable handlers (FEAT-06).

Provides handlers with execution metadata and helper APIs for:
- Reporting incremental task progress to Redis Pub/Sub / SSE
- Uploading binary/text artifacts to configured storage backends
- Accessing task identifiers, attempt numbers, and trace contexts
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from app.core.redis import get_redis
from app.core.storage import get_storage_backend

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
        self._artifacts: list[dict[str, Any]] = []

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

    async def upload_artifact(
        self,
        filename: str,
        data: bytes | str,
        content_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        """Upload an artifact to the active storage backend and record its metadata."""
        storage = get_storage_backend()
        clean_filename = filename.replace("\\", "/").split("/")[-1]
        unique_prefix = uuid.uuid4().hex[:8]
        storage_key = f"tasks/{self.task_id}/artifacts/{unique_prefix}_{clean_filename}"

        raw_bytes = data.encode("utf-8") if isinstance(data, str) else data
        storage.save(storage_key, raw_bytes, content_type=content_type)

        artifact_meta = {
            "storage_key": storage_key,
            "filename": clean_filename,
            "content_type": content_type,
            "size_bytes": len(raw_bytes),
        }
        self._artifacts.append(artifact_meta)
        return artifact_meta

    @property
    def uploaded_artifacts(self) -> list[dict[str, Any]]:
        """List of artifacts uploaded via this context during handler execution."""
        return list(self._artifacts)
