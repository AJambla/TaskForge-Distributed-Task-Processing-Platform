"""Pydantic schemas for task endpoints — per API.md and DATABASE.md."""
import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class TaskType(str, Enum):
    EMAIL_SEND = "email_send"
    IMAGE_RESIZE = "image_resize"
    WEBHOOK_DELIVERY = "webhook_delivery"


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRYING = "retrying"
    DEAD_LETTER = "dead_letter"
    CANCELLED = "cancelled"


class ImageResizePayload(BaseModel):
    source_url: str = Field(..., description="URL of the source image.")
    width: int = Field(..., gt=0, description="Target width in pixels.")
    height: int = Field(..., gt=0, description="Target height in pixels.")


class EmailSendPayload(BaseModel):
    to: str = Field(..., description="Recipient email address.")
    subject: str = Field(..., min_length=1, max_length=256)
    body: str = Field(..., min_length=1)


class WebhookDeliveryPayload(BaseModel):
    url: str = Field(..., description="URL to POST the webhook to.")
    headers: dict[str, str] = Field(default_factory=dict)
    body: dict[str, Any] = Field(default_factory=dict)  # type: ignore[name-defined]


PayloadMap = {
    TaskType.EMAIL_SEND: EmailSendPayload,
    TaskType.IMAGE_RESIZE: ImageResizePayload,
    TaskType.WEBHOOK_DELIVERY: WebhookDeliveryPayload,
}


class TaskCreateRequest(BaseModel):
    task_type: TaskType
    payload: dict[str, Any] = Field(..., description="Task-specific JSON payload.")
    idempotency_key: str | None = Field(
        None,
        max_length=255,
        description="Optional idempotency key for safe retries.",
    )
    priority: int = Field(0, ge=-100, le=100, description="Higher = more urgent.")
    max_attempts: int = Field(
        5, ge=1, le=20, description="Max retry attempts before DLQ."
    )
    run_at: datetime | None = Field(
        None,
        description="Scheduled execution time; defaults to now if null.",
    )

    @field_validator("payload")
    @classmethod
    def validate_payload(cls, v: dict[str, Any], info) -> dict[str, Any]:
        task_type = info.data.get("task_type")
        if task_type and task_type in PayloadMap:
            schema = PayloadMap[task_type]
            try:
                schema.model_validate(v)
            except Exception as exc:
                raise ValueError(f"Invalid payload for {task_type.value}: {exc}") from exc
        return v


class TaskResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    task_type: str
    status: str
    priority: int
    idempotency_key: str | None
    max_attempts: int
    attempt_count: int
    run_at: datetime | None
    recurrence_rule: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class PaginationInfo(BaseModel):
    page: int
    page_size: int
    total: int


class TaskListResponse(BaseModel):
    data: list[TaskResponse]
    pagination: PaginationInfo


class TaskFilter(BaseModel):
    status: TaskStatus | None = None
    task_type: TaskType | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    sort: str = Field("-created_at", description="e.g. -created_at, status, task_type")


class CancelTaskRequest(BaseModel):
    pass


class RetryTaskRequest(BaseModel):
    pass
