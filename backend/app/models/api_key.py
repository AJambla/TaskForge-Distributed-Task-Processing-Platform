"""API Key model — per DATABASE.md § api_keys table."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class APIKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    # SHA-256 hash of the raw key; the raw key is never stored
    key_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    # First few chars shown in UI for identification
    key_prefix: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Non-null means key is revoked; soft-delete to preserve audit trail
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        # Fast auth lookup on every API request — unique index per DATABASE.md
        Index("ix_api_keys_key_hash", "key_hash", unique=True),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="api_keys")  # noqa: F821

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    def __repr__(self) -> str:
        return f"<APIKey id={self.id} prefix={self.key_prefix} user_id={self.user_id}>"
