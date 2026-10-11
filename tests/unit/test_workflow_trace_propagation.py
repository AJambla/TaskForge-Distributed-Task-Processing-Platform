"""Unit tests for Workflow DAG step trace context propagation (FEAT-03)."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tracing import init_tracer
from app.core.workflow_engine import resolve_and_dispatch_downstream
from app.models.task import Task
from app.models.workflow import Workflow, WorkflowStep


@pytest.fixture(autouse=True)
def setup_tracer():
    init_tracer("taskforge-wf-test")


@pytest.mark.asyncio
async def test_resolve_and_dispatch_downstream_propagates_workflow_trace_id():
    """Verify resolve_and_dispatch_downstream links downstream tasks to workflow trace_id."""
    workflow_id = uuid.uuid4()
    wf_trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"

    # Step 1 (completed)
    task1 = Task(id=uuid.uuid4(), task_type="email_send", priority=1, status="succeeded", trace_id=wf_trace_id)
    step1 = WorkflowStep(
        id=uuid.uuid4(),
        workflow_id=workflow_id,
        step_name="step1",
        task_id=task1.id,
        dependencies=[],
        status="succeeded",
        task=task1,
    )

    # Step 2 (dependent on step1, was pending)
    task2 = Task(id=uuid.uuid4(), task_type="webhook_delivery", priority=1, status="pending", payload={"url": "http://example.com"})
    step2 = WorkflowStep(
        id=uuid.uuid4(),
        workflow_id=workflow_id,
        step_name="step2",
        task_id=task2.id,
        dependencies=["step1"],
        status="pending",
        task=task2,
    )

    db = AsyncMock(spec=AsyncSession)

    # Mock first execute (fetching current step)
    step1_res = MagicMock()
    step1_res.scalar_one_or_none.return_value = step1

    # Mock second execute (fetching all steps)
    all_steps_res = MagicMock()
    all_steps_res.scalars.return_value.all.return_value = [step1, step2]

    db.execute.side_effect = [step1_res, all_steps_res]

    with patch("app.core.workflow_engine.publish_task", new_callable=AsyncMock) as mock_pub, \
         patch("app.outbox.service.create_outbox_event", new_callable=AsyncMock) as mock_outbox, \
         patch("app.outbox.service.mark_published", new_callable=AsyncMock):

        mock_event = MagicMock(id=uuid.uuid4())
        mock_outbox.return_value = mock_event

        dispatched = await resolve_and_dispatch_downstream(db, task1.id)

        assert dispatched == [task2.id]
        assert task2.trace_id == wf_trace_id
        mock_outbox.assert_called_once()
        _, kwargs = mock_outbox.call_args
        assert wf_trace_id in kwargs.get("traceparent", "")
        mock_pub.assert_called_once()
