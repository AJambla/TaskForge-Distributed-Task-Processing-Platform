"""Unit tests for task result and signed download endpoints (FEAT-01)."""
import uuid
import pytest
from unittest.mock import AsyncMock, patch

from app.models.task import Task
from app.models.artifact import Artifact
from app.models.user import User
from app.routers.tasks import get_task_result, get_task_download_url
from app.routers.storage import download_local_artifact
from app.core.storage import get_storage_backend
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_get_task_result_success():
    user_id = uuid.uuid4()
    task_id = uuid.uuid4()
    artifact_id = uuid.uuid4()

    user = User(id=user_id, email="owner@test.com", role="user")
    mock_db = AsyncMock()

    task = Task(
        id=task_id,
        user_id=user_id,
        task_type="image_resize",
        status="succeeded",
        result={"format": "PNG", "size_bytes": 100},
    )
    artifact = Artifact(
        id=artifact_id,
        task_id=task_id,
        storage_key=f"tasks/{task_id}/artifacts/image.png",
        filename="image.png",
        content_type="image/png",
        size_bytes=100,
    )
    task.artifacts = [artifact]

    with patch("app.routers.tasks.get_task_with_artifacts", return_value=task):
        res = await get_task_result(task_id=task_id, current_user=user, db=mock_db)

    assert res.task_id == task_id
    assert res.status == "succeeded"
    assert res.result == {"format": "PNG", "size_bytes": 100}
    assert len(res.artifacts) == 1
    assert res.artifacts[0].id == artifact_id
    assert res.artifacts[0].filename == "image.png"


@pytest.mark.asyncio
async def test_get_task_result_ownership_denied():
    user = User(id=uuid.uuid4(), email="other@test.com", role="user")
    task = Task(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        task_type="image_resize",
        status="succeeded",
    )
    mock_db = AsyncMock()

    with patch("app.routers.tasks.get_task_with_artifacts", return_value=task):
        with pytest.raises(HTTPException) as exc_info:
            await get_task_result(task_id=task.id, current_user=user, db=mock_db)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_task_download_url_and_stream(tmp_path):
    user_id = uuid.uuid4()
    task_id = uuid.uuid4()
    artifact_id = uuid.uuid4()

    user = User(id=user_id, email="owner@test.com", role="user")
    mock_db = AsyncMock()

    task = Task(
        id=task_id,
        user_id=user_id,
        task_type="image_resize",
        status="succeeded",
    )
    artifact = Artifact(
        id=artifact_id,
        task_id=task_id,
        storage_key=f"tasks/{task_id}/artifacts/image.png",
        filename="image.png",
        content_type="image/png",
        size_bytes=15,
    )
    task.artifacts = [artifact]

    storage = get_storage_backend()
    storage.save(artifact.storage_key, b"dummy-png-bytes", content_type="image/png")

    with patch("app.routers.tasks.get_task_with_artifacts", return_value=task):
        res = await get_task_download_url(
            task_id=task_id, current_user=user, db=mock_db, artifact_id=artifact_id
        )

    assert res.artifact_id == artifact_id
    assert res.filename == "image.png"
    assert "expires=" in res.download_url
    assert "signature=" in res.download_url
    assert res.expires_in == 900

    # Test downloading via storage router
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(res.download_url)
    qs = parse_qs(parsed.query)
    expires = int(qs["expires"][0])
    sig = qs["signature"][0]

    file_resp = await download_local_artifact(
        storage_key=artifact.storage_key,
        filename=artifact.filename,
        expires=expires,
        signature=sig,
    )
    assert file_resp.path.endswith("image.png")
    assert file_resp.filename == "image.png"

    # Test bad signature rejected with 403
    with pytest.raises(HTTPException) as exc_info:
        await download_local_artifact(
            storage_key=artifact.storage_key,
            filename=artifact.filename,
            expires=expires,
            signature="bad_sig",
        )
    assert exc_info.value.status_code == 403
