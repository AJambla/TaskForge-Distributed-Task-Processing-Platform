"""add result column to tasks and task_attempts

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-11
"""
from collections.abc import Sequence
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0002_add_result_column"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("result", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "task_attempts",
        sa.Column("result", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("task_attempts", "result")
    op.drop_column("tasks", "result")
