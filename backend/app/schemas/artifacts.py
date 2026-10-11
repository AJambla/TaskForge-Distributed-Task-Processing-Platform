"""Pydantic schemas for task artifacts and download links (FEAT-01)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ArtifactItemResponse(BaseModel):
    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class TaskResultResponse(BaseModel):
    task_id: uuid.UUID
    status: str
    result: dict[str, Any] | None = None
    artifacts: list[ArtifactItemResponse] = []


class DownloadUrlResponse(BaseModel):
    artifact_id: uuid.UUID
    filename: str
    download_url: str
    expires_in: int
