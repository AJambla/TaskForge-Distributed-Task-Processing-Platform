"""TaskOutbox model for the Transactional Outbox pattern (IMP-12).

Guarantees zero message loss: written in the same SQL transaction as Task,
then published to RabbitMQ. If publication fails or crashes, background
relay retries until acknowledged.
"""
from __future__ import annotations

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


class TaskOutbox(Base):
    __tablename__ = "task_outbox"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_type: Mapped[str] = mapped_column(String, nullable=False)
    event_type: Mapped[str] = mapped_column(
        String(100), nullable=False, default="task_created", server_default="task_created"
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    traceparent: Mapped[str | None] = mapped_column(String(256), nullable=True)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="pending", server_default="pending"
    )
    retry_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'published', 'failed')",
            name="ck_task_outbox_status",
        ),
        Index("ix_task_outbox_pending", "status", "created_at"),
        Index("ix_task_outbox_claimable", "status", "next_attempt_at", "created_at"),
    )

    task: Mapped["Task"] = relationship("Task")  # type: ignore[name-defined] # noqa: F821
