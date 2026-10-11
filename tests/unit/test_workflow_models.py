"""Unit tests for Workflow and WorkflowStep models (FEAT-04)."""
from __future__ import annotations

import uuid
from app.models.workflow import Workflow, WorkflowStep


def test_create_workflow_and_steps_models():
    user_id = uuid.uuid4()
    wf_id = uuid.uuid4()
    workflow = Workflow(
        id=wf_id,
        user_id=user_id,
        name="Media Ingestion Pipeline",
        status="running",
    )

    task_1 = uuid.uuid4()
    task_2 = uuid.uuid4()

    step_1 = WorkflowStep(
        id=uuid.uuid4(),
        workflow_id=wf_id,
        step_name="download",
        task_id=task_1,
        dependencies=[],
        status="queued",
    )
    step_2 = WorkflowStep(
        id=uuid.uuid4(),
        workflow_id=wf_id,
        step_name="resize",
        task_id=task_2,
        dependencies=["download"],
        status="pending",
    )
    workflow.steps.extend([step_1, step_2])

    assert workflow.name == "Media Ingestion Pipeline"
    assert workflow.status == "running"
    assert len(workflow.steps) == 2
    assert workflow.steps[0].step_name == "download"
    assert workflow.steps[1].dependencies == ["download"]
