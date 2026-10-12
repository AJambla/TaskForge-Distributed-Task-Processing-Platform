"""Pydantic schemas for task endpoints — per API.md and DATABASE.md."""
import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class TaskType(str, Enum):
    EMAIL_SEND = "email_send"
    WEBHOOK_DELIVERY = "webhook_delivery"


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRYING = "retrying"
    DEAD_LETTER = "dead_letter"
    CANCELLED = "cancelled"


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
    TaskType.WEBHOOK_DELIVERY: WebhookDeliveryPayload,
}


class TaskCreateRequest(BaseModel):
    task_type: TaskType | str
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
    recurrence_rule: str | None = Field(
        None,
        max_length=100,
        description="Optional cron expression (e.g. '0 * * * *') for recurring tasks.",
    )

    @field_validator("task_type")
    @classmethod
    def validate_task_type(cls, v: TaskType | str) -> str:
        type_str = v.value if hasattr(v, "value") else str(v)
        from app.worker.handlers import list_handlers
        registered_handlers = list_handlers()
        if type_str not in registered_handlers and type_str not in [t.value for t in TaskType]:
            raise ValueError(
                f"Unknown task_type: '{type_str}'. Task type must be registered with the handler registry."
            )
        return type_str

    @field_validator("recurrence_rule")
    @classmethod
    def validate_recurrence_rule(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v:
                return None
            from croniter import croniter
            if not croniter.is_valid(v):
                raise ValueError(f"Invalid cron expression for recurrence_rule: '{v}'")
        return v

    @field_validator("payload")
    @classmethod
    def validate_payload(cls, v: dict[str, Any], info) -> dict[str, Any]:
        raw_type = info.data.get("task_type")
        if not raw_type:
            return v
        type_str = raw_type.value if hasattr(raw_type, "value") else str(raw_type)

        schema = None
        # Check built-in PayloadMap
        if raw_type in PayloadMap:
            schema = PayloadMap[raw_type]
        else:
            for k, val in PayloadMap.items():
                if k.value == type_str:
                    schema = val
                    break

        # Check pluggable handler schema registry (FEAT-06)
        if schema is None:
            from app.worker.handlers import get_handler_schema
            schema = get_handler_schema(type_str)

        if schema is not None:
            try:
                schema.model_validate(v)
            except Exception as exc:
                raise ValueError(f"Invalid payload for {type_str}: {exc}") from exc
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
    result: dict[str, Any] | None = None
    trace_id: str | None = None
    trace_url: str | None = None

    @classmethod
    def from_task(cls, task: Any) -> "TaskResponse":
        """Build TaskResponse from Task ORM model and interpolate trace_url if trace_id exists."""
        from app.config import get_settings
        settings = get_settings()
        t_id = getattr(task, "trace_id", None)
        t_url = settings.jaeger_ui_url.format(trace_id=t_id) if t_id else None
        data = {
            "id": task.id,
            "user_id": task.user_id,
            "task_type": task.task_type,
            "status": task.status,
            "priority": task.priority,
            "idempotency_key": task.idempotency_key,
            "max_attempts": task.max_attempts,
            "attempt_count": task.attempt_count,
            "run_at": task.run_at,
            "recurrence_rule": task.recurrence_rule,
            "created_at": task.created_at,
            "started_at": task.started_at,
            "completed_at": task.completed_at,
            "result": task.result,
            "trace_id": t_id,
            "trace_url": t_url,
        }
        return cls(**data)

    model_config = {"from_attributes": True}


class PaginationInfo(BaseModel):
    page: int
    page_size: int
    total: int
    next_cursor: str | None = None


class TaskListResponse(BaseModel):
    data: list[TaskResponse]
    pagination: PaginationInfo


class TaskBulkCreateRequest(BaseModel):
    tasks: list[TaskCreateRequest] = Field(
        ..., min_length=1, max_length=1000, description="List of tasks to create (max 1000)."
    )


class TaskBulkResponse(BaseModel):
    submitted_count: int
    tasks: list[TaskResponse]


class TaskResultResponse(BaseModel):
    task_id: uuid.UUID
    status: str
    result: dict[str, Any] | None = None



