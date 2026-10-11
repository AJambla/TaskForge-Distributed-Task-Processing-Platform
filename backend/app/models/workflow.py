"""Workflow and WorkflowStep models for DAG execution (FEAT-04)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="running", server_default="running"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')",
            name="ck_workflows_status",
        ),
    )

    steps: Mapped[list["WorkflowStep"]] = relationship(
        "WorkflowStep", back_populates="workflow", cascade="all, delete-orphan"
    )
    user: Mapped["User"] = relationship("User")  # type: ignore[name-defined] # noqa: F821

    def __repr__(self) -> str:
        return f"<Workflow id={self.id} name={self.name} status={self.status}>"


class WorkflowStep(Base):
    __tablename__ = "workflow_steps"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_name: Mapped[str] = mapped_column(String(100), nullable=False)
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dependencies: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending", server_default="pending"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("workflow_id", "step_name", name="uq_workflow_step_name"),
        CheckConstraint(
            "status IN ('pending', 'queued', 'running', 'succeeded', 'failed')",
            name="ck_workflow_steps_status",
        ),
        Index("ix_workflow_steps_workflow", "workflow_id"),
    )

    workflow: Mapped["Workflow"] = relationship("Workflow", back_populates="steps")
    task: Mapped["Task"] = relationship("Task")  # type: ignore[name-defined] # noqa: F821

    def __repr__(self) -> str:
        return f"<WorkflowStep id={self.id} step={self.step_name} status={self.status}>"
