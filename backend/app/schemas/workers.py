"""Pydantic schemas for worker admin endpoints."""
import uuid
from datetime import datetime

from pydantic import BaseModel


class TaskAttemptResponse(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    attempt_number: int
    worker_id: uuid.UUID | None
    started_at: datetime
    finished_at: datetime | None
    outcome: str | None
    error_message: str | None

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

    model_config = {"from_attributes": True}
