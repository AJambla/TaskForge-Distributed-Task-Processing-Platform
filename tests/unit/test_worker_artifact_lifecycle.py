"""Unit tests for worker lifecycle artifact persistence and image handler (FEAT-01)."""
import uuid
import pytest
from unittest.mock import AsyncMock, patch

from app.models.task import Task
from app.models.task_attempt import TaskAttempt
from app.models.artifact import Artifact
from app.worker.lifecycle import mark_success


@pytest.mark.asyncio
async def test_mark_success_persists_artifact_records():
    mock_db = AsyncMock()
    # Mock execute/scalars for any subsequent queries if needed
    task = Task(id=uuid.uuid4(), status="running")
    attempt = TaskAttempt(id=uuid.uuid4(), task_id=task.id)

    artifact_data = {
        "storage_key": f"tasks/{task.id}/artifacts/image.png",
        "filename": "image.png",
        "content_type": "image/png",
        "size_bytes": 48392,
    }
    handler_result = {
        "format": "PNG",
        "size_bytes": 48392,
        "artifacts": [artifact_data],
    }

    with patch("app.worker.lifecycle.update_worker_stats", new_callable=AsyncMock):
        await mark_success(mock_db, task, attempt, result=handler_result)

    assert task.status == "succeeded"
    assert task.result == handler_result

    # Verify db.add was called for Artifact
    added_objects = [call.args[0] for call in mock_db.add.call_args_list]
    artifacts_added = [obj for obj in added_objects if isinstance(obj, Artifact)]
    assert len(artifacts_added) == 1
    art = artifacts_added[0]
    assert art.task_id == task.id
    assert art.storage_key == artifact_data["storage_key"]
    assert art.filename == "image.png"
    assert art.content_type == "image/png"
    assert art.size_bytes == 48392
