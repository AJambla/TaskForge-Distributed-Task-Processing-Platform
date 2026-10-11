"""Unit tests for Workflow DAG Transactional Outbox integration (FEAT-02)."""
import uuid
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.user import User
from app.models.workflow import Workflow, WorkflowStep
from app.models.task import Task
from app.models.task_outbox import TaskOutbox
from app.schemas.workflows import WorkflowCreateRequest, WorkflowStepCreate
from app.routers.workflows import create_workflow
from app.core.workflow_engine import resolve_and_dispatch_downstream


@pytest.mark.asyncio
async def test_create_workflow_writes_root_tasks_to_outbox():
    user = User(id=uuid.uuid4(), email="dev@test.com", role="user")
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()

    body = WorkflowCreateRequest(
        name="Outbox Workflow",
        steps=[
            WorkflowStepCreate(step_name="root", task_type="email_send", dependencies=[]),
            WorkflowStepCreate(step_name="child", task_type="image_resize", dependencies=["root"]),
        ],
    )

    with patch("app.routers.workflows.publish_task", new_callable=AsyncMock) as mock_pub:
        # Mock reload query in create_workflow
        mock_wf = Workflow(
            id=uuid.uuid4(),
            user_id=user.id,
            name="Outbox Workflow",
            status="running",
            created_at=datetime.now(timezone.utc),
        )
        mock_wf.steps = []
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = mock_wf
        mock_db.execute.return_value = mock_result

        await create_workflow(body=body, current_user=user, db=mock_db)

    # Verify TaskOutbox was added to session for root step
    added_items = [call[0][0] for call in mock_db.add.call_args_list]
    outbox_entries = [item for item in added_items if isinstance(item, TaskOutbox)]
    assert len(outbox_entries) == 1
    assert outbox_entries[0].task_type == "email_send"
    assert outbox_entries[0].event_type == "workflow_root_step"


@pytest.mark.asyncio
async def test_resolve_downstream_writes_unblocked_tasks_to_outbox():
    mock_db = AsyncMock()
    wf_id = uuid.uuid4()
    parent_task_id = uuid.uuid4()
    child_task_id = uuid.uuid4()

    parent_task = Task(id=parent_task_id, task_type="email_send", status="succeeded")
    child_task = Task(id=child_task_id, task_type="image_resize", status="pending")

    wf = Workflow(id=wf_id, status="running")
    step_parent = WorkflowStep(
        workflow_id=wf_id, step_name="parent", task_id=parent_task_id, dependencies=[], status="running"
    )
    step_parent.workflow = wf
    step_parent.task = parent_task

    step_child = WorkflowStep(
        workflow_id=wf_id, step_name="child", task_id=child_task_id, dependencies=["parent"], status="pending"
    )
    step_child.workflow = wf
    step_child.task = child_task

    # Mock execute for step_res and all_steps_res
    res_single = MagicMock()
    res_single.scalar_one_or_none.return_value = step_parent

    res_all = MagicMock()
    res_all.scalars.return_value.all.return_value = [step_parent, step_child]

    mock_db.execute.side_effect = [res_single, res_all]
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    with patch("app.core.workflow_engine.publish_task", new_callable=AsyncMock):
        dispatched = await resolve_and_dispatch_downstream(mock_db, parent_task_id)

    assert child_task_id in dispatched
    added_items = [call[0][0] for call in mock_db.add.call_args_list]
    outbox_entries = [item for item in added_items if isinstance(item, TaskOutbox)]
    assert len(outbox_entries) == 1
    assert outbox_entries[0].task_id == child_task_id
    assert outbox_entries[0].task_type == "image_resize"
    assert outbox_entries[0].event_type == "workflow_step_queued"
