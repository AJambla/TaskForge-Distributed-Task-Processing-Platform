"""Pydantic schemas for Workflows and DAG execution (FEAT-04)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class WorkflowStepCreate(BaseModel):
    step_name: str = Field(..., min_length=1, max_length=100, description="Unique identifier for step within workflow")
    task_type: str = Field(..., description="Task type (e.g., email_send, image_resize)")
    payload: dict[str, Any] = Field(default_factory=dict, description="Input payload for task execution")
    priority: int = Field(default=0, ge=0, le=10, description="Task priority (0-10)")
    dependencies: list[str] = Field(default_factory=list, description="List of step_names that must succeed before this step")


class WorkflowCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Human-readable name of the workflow")
    steps: list[WorkflowStepCreate] = Field(..., min_length=1, description="List of DAG steps")


class WorkflowStepResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    step_name: str
    task_id: uuid.UUID
    dependencies: list[str]
    status: str
    created_at: datetime


class WorkflowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    status: str
    created_at: datetime
    completed_at: datetime | None = None
    steps: list[WorkflowStepResponse] = Field(default_factory=list)


class WorkflowListResponse(BaseModel):
    total: int
    items: list[WorkflowResponse]
