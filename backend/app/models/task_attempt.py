"""TaskAttempt model — per DATABASE.md § task_attempts table."""
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
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class TaskAttempt(Base):
    __tablename__ = "task_attempts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # Nullable: worker_id is null if task was never picked up
    worker_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("worker_registrations.id", ondelete="SET NULL"),
        nullable=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Nullable until the attempt finishes
    outcome: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "outcome IN ('success', 'failure', 'timeout')",
            name="ck_task_attempts_outcome",
        ),
        # Per DATABASE.md: attempt-history retrieval for Task Detail view
        Index("ix_task_attempts_task_id_attempt_number", "task_id", "attempt_number"),
    )

    # Relationships
    task: Mapped["Task"] = relationship("Task", back_populates="attempts")  # noqa: F821
    worker: Mapped["WorkerRegistration | None"] = relationship(  # noqa: F821
        "WorkerRegistration", back_populates="attempts"
    )

    def __repr__(self) -> str:
        return f"<TaskAttempt id={self.id} task_id={self.task_id} attempt={self.attempt_number} outcome={self.outcome}>"
