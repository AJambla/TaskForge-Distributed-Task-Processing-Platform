"""Pydantic schemas for worker admin endpoints."""
import uuid
from datetime import datetime

from pydantic import BaseModel, computed_field


class TaskAttemptResponse(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    attempt_number: int
    worker_id: uuid.UUID | None
    started_at: datetime
    finished_at: datetime | None
    outcome: str | None
    error_message: str | None
    trace_id: str | None = None

    model_config = {"from_attributes": True}


class WorkerListItem(BaseModel):
    id: uuid.UUID
    hostname: str
    status: str
    concurrency_limit: int
    current_task_count: int
    last_heartbeat_at: datetime
    tasks_processed: int
    tasks_failed: int
    registered_at: datetime

    @computed_field
    @property
    def utilization_rate(self) -> float:
        count = self.current_task_count or 0
        limit = self.concurrency_limit or 1
        return round(count / max(1, limit), 4)

    model_config = {"from_attributes": True}


class WorkerDetail(BaseModel):
    id: uuid.UUID
    hostname: str
    status: str
    concurrency_limit: int
    current_task_count: int
    last_heartbeat_at: datetime
    tasks_processed: int
    tasks_failed: int
    registered_at: datetime
    recent_attempts: list[TaskAttemptResponse]

    @computed_field
    @property
    def utilization_rate(self) -> float:
        count = self.current_task_count or 0
        limit = self.concurrency_limit or 1
        return round(count / max(1, limit), 4)

    model_config = {"from_attributes": True}

