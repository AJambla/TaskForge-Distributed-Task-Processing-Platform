"""Alembic migration: Enhance task_outbox with retry and backoff fields (FEAT-02).

Revision ID: 0008_enhance_task_outbox_retry_fields
Revises: 0005_add_organizations_and_memberships
Create Date: 2026-10-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_enhance_task_outbox_retry_fields"
down_revision = "0005_add_organizations_and_memberships"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "task_outbox",
        sa.Column(
            "event_type",
            sa.String(100),
            nullable=False,
            server_default="task_created",
        ),
    )
    op.add_column(
        "task_outbox",
        sa.Column(
            "last_attempt_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "task_outbox",
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.add_column(
        "task_outbox",
        sa.Column(
            "last_error",
            sa.Text(),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_task_outbox_claimable",
        "task_outbox",
        ["status", "next_attempt_at", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_task_outbox_claimable", table_name="task_outbox")
    op.drop_column("task_outbox", "last_error")
    op.drop_column("task_outbox", "next_attempt_at")
    op.drop_column("task_outbox", "last_attempt_at")
    op.drop_column("task_outbox", "event_type")
