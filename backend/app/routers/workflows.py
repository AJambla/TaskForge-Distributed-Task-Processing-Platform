"""Workflow router for submitting and querying multi-step DAG workflows (FEAT-04)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.deps import CurrentUser, DBSession
from app.core.rabbitmq import publish_task
from app.core.workflow_engine import validate_dag
from app.models.task import Task
from app.models.workflow import Workflow, WorkflowStep
from app.schemas.workflows import (
    WorkflowCreateRequest,
    WorkflowListResponse,
    WorkflowResponse,
)

logger = logging.getLogger("workflow.router")
router = APIRouter(prefix="/workflows", tags=["Workflows"])


@router.post("", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED, summary="Submit a DAG workflow")
async def create_workflow(
    body: WorkflowCreateRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> WorkflowResponse:
    """Submit a multi-step DAG workflow with dependencies."""
    steps_data = [s.model_dump() for s in body.steps]
    try:
        validate_dag(steps_data)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "INVALID_WORKFLOW_DAG",
                    "message": str(exc),
                    "field": "steps",
                }
            },
        )

    workflow = Workflow(
        user_id=current_user.id,
        name=body.name,
        status="running",
    )
    db.add(workflow)
    await db.flush()

    ready_tasks_to_publish: list[tuple[Task, str, int]] = []

    for step_in in body.steps:
        # Steps with zero dependencies start queued immediately; others wait as pending
        is_root = len(step_in.dependencies) == 0
        task_status = "queued" if is_root else "pending"
        step_status = "queued" if is_root else "pending"

        task = Task(
            user_id=current_user.id,
            task_type=step_in.task_type,
            payload=step_in.payload,
            status=task_status,
            priority=step_in.priority,
            run_at=datetime.now(timezone.utc) if is_root else None,
        )
        db.add(task)
        await db.flush()

        step = WorkflowStep(
            workflow_id=workflow.id,
            step_name=step_in.step_name,
            task_id=task.id,
            dependencies=step_in.dependencies,
            status=step_status,
        )
        db.add(step)
        if is_root:
            ready_tasks_to_publish.append((task, step_in.task_type, step_in.priority))

    await db.commit()

    # Publish root tasks
    for task_obj, t_type, prio in ready_tasks_to_publish:
        try:
            await publish_task(str(task_obj.id), t_type, priority=prio)
        except Exception as exc:
            logger.warning("Failed to publish root workflow task %s: %s", task_obj.id, exc)

    # Reload with steps
    res = await db.execute(
        select(Workflow)
        .where(Workflow.id == workflow.id)
        .options(selectinload(Workflow.steps))
    )
    loaded_wf = res.scalar_one()
    return WorkflowResponse.model_validate(loaded_wf)


@router.get("", response_model=WorkflowListResponse, summary="List workflows")
async def list_workflows(
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> WorkflowListResponse:
    """List workflows for the current user."""
    is_admin = current_user.role == "admin"
    base_q = select(Workflow)
    if not is_admin:
        base_q = base_q.where(Workflow.user_id == current_user.id)

    count_q = select(func.count()).select_from(base_q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    offset = (page - 1) * page_size
    query = (
        base_q.options(selectinload(Workflow.steps))
        .order_by(Workflow.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    items = (await db.execute(query)).scalars().all()

    return WorkflowListResponse(
        total=total,
        items=[WorkflowResponse.model_validate(w) for w in items],
    )


@router.get("/{workflow_id}", response_model=WorkflowResponse, summary="Get workflow details")
async def get_workflow(
    workflow_id: UUID,
    current_user: CurrentUser,
    db: DBSession,
) -> WorkflowResponse:
    """Retrieve details and step status of a single workflow."""
    is_admin = current_user.role == "admin"
    query = (
        select(Workflow)
        .where(Workflow.id == workflow_id)
        .options(selectinload(Workflow.steps))
    )
    if not is_admin:
        query = query.where(Workflow.user_id == current_user.id)

    wf = (await db.execute(query)).scalar_one_or_none()
    if not wf:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "WORKFLOW_NOT_FOUND",
                    "message": "Workflow not found or access denied.",
                    "field": None,
                }
            },
        )
    return WorkflowResponse.model_validate(wf)
