"""Workflow DAG validation and downstream resolution engine (FEAT-04)."""
from __future__ import annotations

import logging
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.rabbitmq import publish_task
from app.models.task import Task
from app.models.workflow import Workflow, WorkflowStep

logger = logging.getLogger("workflow.engine")


def validate_dag(steps: list[dict[str, Any]]) -> list[str]:
    """Validate that workflow steps form a valid Directed Acyclic Graph (DAG).

    Returns topological ordering of step names.
    Raises ValueError on empty steps, duplicates, unknown dependencies, or cycles.
    """
    if not steps:
        raise ValueError("Workflow must have at least one step.")

    step_names: set[str] = set()
    in_degree: dict[str, int] = {}
    adj: dict[str, list[str]] = defaultdict(list)

    for s in steps:
        name = s.get("step_name")
        if not name:
            raise ValueError("Every step must specify a non-empty 'step_name'.")
        if name in step_names:
            raise ValueError(f"Duplicate step name '{name}' detected in workflow.")
        step_names.add(name)
        in_degree[name] = 0

    # Build adjacency and compute in-degrees
    for s in steps:
        name = s["step_name"]
        deps = s.get("dependencies") or []
        for dep in deps:
            if dep not in step_names:
                raise ValueError(f"Step '{name}' depends on unknown step '{dep}'.")
            adj[dep].append(name)
            in_degree[name] += 1

    # Kahn's algorithm
    queue: deque[str] = deque([name for name, deg in in_degree.items() if deg == 0])
    ordered: list[str] = []

    while queue:
        node = queue.popleft()
        ordered.append(node)
        for neighbor in adj[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(ordered) != len(step_names):
        raise ValueError("Cyclic dependency detected in workflow DAG.")

    return ordered


async def resolve_and_dispatch_downstream(db: AsyncSession, completed_task_id: UUID) -> list[UUID]:
    """Called on task completion to advance workflow state and dispatch ready downstream tasks."""
    # Check if task is part of a workflow
    step_res = await db.execute(
        select(WorkflowStep)
        .where(WorkflowStep.task_id == completed_task_id)
        .options(selectinload(WorkflowStep.workflow))
    )
    current_step = step_res.scalar_one_or_none()
    if not current_step:
        return []

    current_step.status = "succeeded"
    workflow_id = current_step.workflow_id

    # Fetch all steps in the workflow
    all_steps_res = await db.execute(
        select(WorkflowStep)
        .where(WorkflowStep.workflow_id == workflow_id)
        .options(selectinload(WorkflowStep.task))
    )
    all_steps = all_steps_res.scalars().all()

    succeeded_steps = {s.step_name for s in all_steps if s.status == "succeeded"}
    dispatched_task_ids: list[UUID] = []

    # Evaluate candidate pending steps
    for step in all_steps:
        if step.status == "pending":
            deps = step.dependencies or []
            # If all required dependencies are satisfied
            if all(d in succeeded_steps for d in deps):
                step.status = "queued"
                if step.task:
                    step.task.status = "queued"
                    step.task.run_at = datetime.now(timezone.utc)
                    from app.core.tracing import create_traceparent
                    step_trace_id = getattr(step.task, "trace_id", None)
                    if not step_trace_id:
                        # Fallback: check if other steps in workflow have trace_id
                        for s in all_steps:
                            if s.task and getattr(s.task, "trace_id", None):
                                step_trace_id = s.task.trace_id
                                break
                    if not step_trace_id:
                        step_trace_id = create_traceparent().split("-")[1]
                    step.task.trace_id = step_trace_id
                    step_traceparent = create_traceparent(trace_id=step_trace_id)

                    from app.outbox.service import create_outbox_event, mark_published
                    outbox_entry = await create_outbox_event(
                        db=db,
                        task_id=step.task.id,
                        task_type=step.task.task_type,
                        payload=step.task.payload or {},
                        priority=step.task.priority,
                        event_type="workflow_step_queued",
                        traceparent=step_traceparent,
                    )
                    dispatched_task_ids.append(step.task.id)
                    try:
                        await publish_task(
                            str(step.task.id),
                            step.task.task_type,
                            priority=step.task.priority,
                            traceparent=step_traceparent,
                        )
                        await mark_published(db, outbox_entry.id)
                    except Exception as pub_exc:
                        logger.warning(
                            "Failed immediate publish for workflow step task %s: %s (outbox relay will retry)",
                            step.task.id,
                            pub_exc,
                        )
                    logger.info(
                        "Dispatched workflow %s step '%s' (task=%s, trace=%s)",
                        workflow_id,
                        step.step_name,
                        step.task.id,
                        step_trace_id,
                    )

    # Check if entire workflow has completed
    all_succeeded = all(s.status == "succeeded" for s in all_steps)
    if all_succeeded:
        wf = current_step.workflow
        if wf:
            wf.status = "succeeded"
            wf.completed_at = datetime.now(timezone.utc)
            logger.info("Workflow %s completed successfully.", workflow_id)

    await db.commit()
    return dispatched_task_ids


async def handle_step_failure(db: AsyncSession, failed_task_id: UUID) -> None:
    """Called on terminal task failure to mark workflow and step as failed."""
    step_res = await db.execute(
        select(WorkflowStep)
        .where(WorkflowStep.task_id == failed_task_id)
        .options(selectinload(WorkflowStep.workflow))
    )
    current_step = step_res.scalar_one_or_none()
    if not current_step:
        return

    current_step.status = "failed"
    if current_step.workflow:
        current_step.workflow.status = "failed"
        current_step.workflow.completed_at = datetime.now(timezone.utc)
        logger.warning(
            "Workflow %s marked failed due to step '%s' failure.",
            current_step.workflow_id,
            current_step.step_name,
        )

    await db.commit()
