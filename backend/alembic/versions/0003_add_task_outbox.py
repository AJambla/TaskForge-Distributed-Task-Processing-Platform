"""Alembic migration: Add task_outbox table (IMP-12).

Revision ID: 0003_add_task_outbox
Revises: 0002_add_result_column
Create Date: 2026-10-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0003_add_task_outbox"
down_revision = "0002_add_result_column"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_type", sa.String(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("priority", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("retry_count", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('pending', 'published', 'failed')", name="ck_task_outbox_status"),
    )
    op.create_index("ix_task_outbox_pending", "task_outbox", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_task_outbox_pending", table_name="task_outbox")
    op.drop_table("task_outbox")
