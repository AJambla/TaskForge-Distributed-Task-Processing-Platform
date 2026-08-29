"""WorkerRegistration model — per DATABASE.md § worker_registrations table."""
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class WorkerRegistration(Base):
    __tablename__ = "worker_registrations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    hostname: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="online")
    concurrency_limit: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    current_task_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0
    )
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    tasks_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tasks_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        CheckConstraint(
            "status IN ('online', 'offline', 'draining')",
            name="ck_worker_registrations_status",
        ),
        # Per DATABASE.md: periodic job marks workers offline after missed heartbeat
        Index("ix_worker_registrations_last_heartbeat_at", "last_heartbeat_at"),
    )

    # Relationships
    attempts: Mapped[list["TaskAttempt"]] = relationship(  # noqa: F821
        "TaskAttempt", back_populates="worker"
    )

    def __repr__(self) -> str:
        return f"<WorkerRegistration id={self.id} hostname={self.hostname} status={self.status}>"
