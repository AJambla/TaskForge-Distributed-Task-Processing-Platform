"""Alembic migration: Add workflows and workflow_steps tables (FEAT-04).

Revision ID: 0006_add_workflows_and_workflow_steps
Revises: 0005_add_organizations_and_memberships
Create Date: 2026-10-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_add_workflows_and_workflow_steps"
down_revision = "0005_add_organizations_and_memberships"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="running"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('running', 'succeeded', 'failed')", name="ck_workflows_status"),
    )
    op.create_index("ix_workflows_user_id", "workflows", ["user_id"])

    op.create_table(
        "workflow_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_name", sa.String(100), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dependencies", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("workflow_id", "step_name", name="uq_workflow_step_name"),
        sa.CheckConstraint("status IN ('pending', 'queued', 'running', 'succeeded', 'failed')", name="ck_workflow_steps_status"),
    )
    op.create_index("ix_workflow_steps_workflow", "workflow_steps", ["workflow_id"])
    op.create_index("ix_workflow_steps_task_id", "workflow_steps", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_workflow_steps_task_id", table_name="workflow_steps")
    op.drop_index("ix_workflow_steps_workflow", table_name="workflow_steps")
    op.drop_table("workflow_steps")
    op.drop_index("ix_workflows_user_id", table_name="workflows")
    op.drop_table("workflows")
