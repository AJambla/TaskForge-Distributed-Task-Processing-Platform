"""add_tracing_fields

Revision ID: 0009_add_tracing_fields
Revises: 0008_enhance_task_outbox_retry_fields
Create Date: 2026-10-12

"""
from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa


revision: str = "0009_add_tracing_fields"
down_revision: str | None = "0008_enhance_task_outbox_retry_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("trace_id", sa.String(length=32), nullable=True))
    op.create_index(op.f("ix_tasks_trace_id"), "tasks", ["trace_id"], unique=False)

    op.add_column("task_attempts", sa.Column("trace_id", sa.String(length=32), nullable=True))
    op.create_index(op.f("ix_task_attempts_trace_id"), "task_attempts", ["trace_id"], unique=False)

    op.add_column("task_outbox", sa.Column("traceparent", sa.String(length=256), nullable=True))


def downgrade() -> None:
    op.drop_column("task_outbox", "traceparent")
    op.drop_index(op.f("ix_task_attempts_trace_id"), table_name="task_attempts")
    op.drop_column("task_attempts", "trace_id")
    op.drop_index(op.f("ix_tasks_trace_id"), table_name="tasks")
    op.drop_column("tasks", "trace_id")
