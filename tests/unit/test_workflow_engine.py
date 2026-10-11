"""Unit tests for DAG validation and step resolution engine (FEAT-04)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.core.workflow_engine import (
    handle_step_failure,
    resolve_and_dispatch_downstream,
    validate_dag,
)
from app.models.task import Task
from app.models.workflow import Workflow, WorkflowStep


def test_validate_dag_empty_raises_error():
    with pytest.raises(ValueError, match="Workflow must have at least one step"):
        validate_dag([])


def test_validate_dag_duplicate_step_names():
    steps = [
        {"step_name": "step_a", "dependencies": []},
        {"step_name": "step_a", "dependencies": []},
    ]
    with pytest.raises(ValueError, match="Duplicate step name 'step_a'"):
        validate_dag(steps)


def test_validate_dag_unknown_dependency():
    steps = [
        {"step_name": "step_a", "dependencies": ["non_existent"]},
    ]
    with pytest.raises(ValueError, match="depends on unknown step 'non_existent'"):
        validate_dag(steps)


def test_validate_dag_detects_cycles():
    # Direct cycle
    steps = [
        {"step_name": "a", "dependencies": ["b"]},
        {"step_name": "b", "dependencies": ["a"]},
    ]
    with pytest.raises(ValueError, match="Cyclic dependency detected"):
        validate_dag(steps)

    # 3-step cycle
    steps_3 = [
        {"step_name": "a", "dependencies": ["c"]},
        {"step_name": "b", "dependencies": ["a"]},
        {"step_name": "c", "dependencies": ["b"]},
    ]
    with pytest.raises(ValueError, match="Cyclic dependency detected"):
        validate_dag(steps_3)


def test_validate_dag_valid_topological_sort():
    # Fan-out / Fan-in diamond: start -> [process_1, process_2] -> aggregate
    steps = [
        {"step_name": "start", "dependencies": []},
        {"step_name": "process_1", "dependencies": ["start"]},
        {"step_name": "process_2", "dependencies": ["start"]},
        {"step_name": "aggregate", "dependencies": ["process_1", "process_2"]},
    ]
    order = validate_dag(steps)
    assert order[0] == "start"
    assert order[-1] == "aggregate"
    assert set(order[1:3]) == {"process_1", "process_2"}


@pytest.mark.asyncio
async def test_resolve_and_dispatch_downstream_fan_in_barrier():
    wf_id = uuid.uuid4()
    workflow = Workflow(id=wf_id, user_id=uuid.uuid4(), name="Pipeline", status="running")

    task_1 = Task(id=uuid.uuid4(), user_id=workflow.user_id, task_type="email_send", status="succeeded")
    task_2 = Task(id=uuid.uuid4(), user_id=workflow.user_id, task_type="email_send", status="running")
    task_3 = Task(id=uuid.uuid4(), user_id=workflow.user_id, task_type="email_send", status="pending")

    step_1 = WorkflowStep(
        id=uuid.uuid4(), workflow_id=wf_id, step_name="b1", task_id=task_1.id, dependencies=[], status="running"
    )
    step_2 = WorkflowStep(
        id=uuid.uuid4(), workflow_id=wf_id, step_name="b2", task_id=task_2.id, dependencies=[], status="running"
    )
    step_3 = WorkflowStep(
        id=uuid.uuid4(), workflow_id=wf_id, step_name="agg", task_id=task_3.id, dependencies=["b1", "b2"], status="pending"
    )

    step_1.workflow = workflow
    step_1.task = task_1
    step_2.workflow = workflow
    step_2.task = task_2
    step_3.workflow = workflow
    step_3.task = task_3
    workflow.steps = [step_1, step_2, step_3]

    mock_db = AsyncMock()
    # Query for step by completed task_id
    mock_res_step = MagicMock()
    mock_res_step.scalar_one_or_none.return_value = step_1

    # Query for all steps in workflow
    mock_res_all = MagicMock()
    mock_res_all.scalars.return_value.all.return_value = [step_1, step_2, step_3]

    mock_db.execute.side_effect = [mock_res_step, mock_res_all]

    with patch("app.core.workflow_engine.publish_task") as mock_publish:
        dispatched = await resolve_and_dispatch_downstream(mock_db, task_1.id)
        # step_3 depends on b1 AND b2. b2 is not succeeded yet, so step_3 must NOT dispatch!
        assert dispatched == []
        assert step_1.status == "succeeded"
        assert step_3.status == "pending"
        mock_publish.assert_not_called()
