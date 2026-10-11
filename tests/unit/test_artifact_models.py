"""Unit tests for Artifact model (FEAT-01)."""
import uuid
from datetime import datetime, timezone

from app.models.artifact import Artifact


def test_artifact_model_initialization():
    task_id = uuid.uuid4()
    artifact = Artifact(
        task_id=task_id,
        storage_key="tasks/123/artifacts/image.png",
        filename="image.png",
        content_type="image/png",
        size_bytes=1024,
    )
    assert artifact.task_id == task_id
    assert artifact.storage_key == "tasks/123/artifacts/image.png"
    assert artifact.filename == "image.png"
    assert artifact.content_type == "image/png"
    assert artifact.size_bytes == 1024
