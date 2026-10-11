"""Unit tests for Workflow API endpoints (FEAT-04)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.models.user import User
from app.models.workflow import Workflow, WorkflowStep
from app.routers.workflows import create_workflow, get_workflow, list_workflows
from app.schemas.workflows import WorkflowCreateRequest, WorkflowStepCreate
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_create_workflow_rejects_cyclic_dag():
    user = User(id=uuid.uuid4(), email="dev@example.com", role="user")
    mock_db = AsyncMock()

    body = WorkflowCreateRequest(
        name="Cyclic Graph",
        steps=[
            WorkflowStepCreate(step_name="a", task_type="email_send", dependencies=["b"]),
            WorkflowStepCreate(step_name="b", task_type="email_send", dependencies=["a"]),
        ],
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_workflow(body=body, current_user=user, db=mock_db)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["error"]["code"] == "INVALID_WORKFLOW_DAG"


@pytest.mark.asyncio
async def test_create_workflow_success_and_publishes_root_tasks():
    user = User(id=uuid.uuid4(), email="dev@example.com", role="user")
    mock_db = AsyncMock()
    wf_id = uuid.uuid4()

    now = datetime.now(timezone.utc)
    mock_wf = Workflow(id=wf_id, user_id=user.id, name="Valid Pipeline", status="running", created_at=now)
    mock_step_1 = WorkflowStep(id=uuid.uuid4(), workflow_id=wf_id, step_name="root", task_id=uuid.uuid4(), dependencies=[], status="queued", created_at=now)
    mock_step_2 = WorkflowStep(id=uuid.uuid4(), workflow_id=wf_id, step_name="child", task_id=uuid.uuid4(), dependencies=["root"], status="pending", created_at=now)
    mock_wf.steps = [mock_step_1, mock_step_2]

    # Reload query mock
    mock_res = MagicMock()
    mock_res.scalar_one.return_value = mock_wf
    mock_db.execute.return_value = mock_res

    body = WorkflowCreateRequest(
        name="Valid Pipeline",
        steps=[
            WorkflowStepCreate(step_name="root", task_type="email_send", dependencies=[]),
            WorkflowStepCreate(step_name="child", task_type="email_send", dependencies=["root"]),
        ],
    )

    with patch("app.routers.workflows.publish_task") as mock_publish:
        res = await create_workflow(body=body, current_user=user, db=mock_db)
        assert res.name == "Valid Pipeline"
        assert res.status == "running"
        assert len(res.steps) == 2
        mock_publish.assert_called_once()


@pytest.mark.asyncio
async def test_get_workflow_404_when_not_found():
    user = User(id=uuid.uuid4(), email="dev@example.com", role="user")
    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_res

    with pytest.raises(HTTPException) as exc_info:
        await get_workflow(workflow_id=uuid.uuid4(), current_user=user, db=mock_db)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error"]["code"] == "WORKFLOW_NOT_FOUND"
