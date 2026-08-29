"""Task model — per DATABASE.md § tasks table."""
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_type: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="queued")
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    idempotency_key: Mapped[str | None] = mapped_column(String, nullable=True)
    max_attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=5)
    attempt_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, server_default=func.now()
    )
    recurrence_rule: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "task_type IN ('email_send', 'image_resize', 'webhook_delivery')",
            name="ck_tasks_task_type",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'retrying', 'dead_letter', 'cancelled')",
            name="ck_tasks_status",
        ),
        # Per DATABASE.md: (user_id, status) for task-list filtering
        Index("ix_tasks_user_id_status", "user_id", "status"),
        # Per DATABASE.md: (status, run_at) for scheduler/worker pickup
        Index("ix_tasks_status_run_at", "status", "run_at"),
        # Per DATABASE.md: unique idempotency per user — partial index (only when key present)
        UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_tasks_user_idempotency_key",
            # PostgreSQL partial unique constraint handled at migration level
        ),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="tasks")  # noqa: F821
    attempts: Mapped[list["TaskAttempt"]] = relationship(  # noqa: F821
        "TaskAttempt",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="TaskAttempt.attempt_number",
    )

    def __repr__(self) -> str:
        return f"<Task id={self.id} type={self.task_type} status={self.status}>"
