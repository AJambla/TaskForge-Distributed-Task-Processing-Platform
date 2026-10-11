"""Alembic migration: Add schedules table and task.schedule_id (IMP-13).

Revision ID: 0004_add_schedules_table
Revises: 0003_add_task_outbox
Create Date: 2026-10-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0004_add_schedules_table"
down_revision = "0003_add_task_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("task_type", sa.String(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("recurrence_rule", sa.Text(), nullable=False),
        sa.Column("timezone", sa.String(50), nullable=False, server_default="UTC"),
        sa.Column("is_paused", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("task_type IN ('email_send', 'image_resize', 'webhook_delivery')", name="ck_schedules_task_type"),
    )
    op.create_index("ix_schedules_next_run", "schedules", ["is_paused", "next_run_at"])

    op.add_column(
        "tasks",
        sa.Column(
            "schedule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("schedules.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("tasks", "schedule_id")
    op.drop_index("ix_schedules_next_run", table_name="schedules")
    op.drop_table("schedules")
