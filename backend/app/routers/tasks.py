"""Task router — submit, list, retrieve, cancel, and retry tasks.

Per API.md:
- POST   /api/v1/tasks          — create (with idempotency)
- GET    /api/v1/tasks          — list (paginated, filterable, sortable)
- GET    /api/v1/tasks/{id}     — retrieve single task
- POST   /api/v1/tasks/{id}/cancel — cancel a queued/retrying task
- POST   /api/v1/tasks/{id}/retry  — re-queue a failed/dead_letter task
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.core.deps import CurrentUser, DBSession
from app.core.rabbitmq import check_backpressure, publish_task
from app.core.rate_limit import RateLimiter
from app.core.redis import check_idempotency, set_idempotency_task_id
from app.models.task import Task
from app.schemas.tasks import (
    PaginationInfo,
    TaskCreateRequest,
    TaskListResponse,
    TaskResponse,
    TaskStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a new task",
)
async def create_task(
    body: TaskCreateRequest,
    current_user: CurrentUser,
    db: DBSession,
    rate_limit: Annotated[None, Depends(RateLimiter(limit=get_settings().rate_limit_task_submission_per_minute))],
    idempotency_key_header: str | None = Query(
        None,
        alias="Idempotency-Key",
        description="Alternative body idempotency key (header takes precedence).",
    ),
) -> TaskResponse:
    """Submit a task for processing with idempotency protection."""
    idempotency_key = idempotency_key_header or body.idempotency_key

    if idempotency_key:
        already = await check_idempotency(
            str(current_user.id), idempotency_key
        )
        if already:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": {
                        "code": "DUPLICATE_IDEMPOTENCY_KEY",
                        "message": f"Task with idempotency key '{idempotency_key}' already exists.",
                        "field": "idempotency_key",
                    }
                },
            )

    now = datetime.now(timezone.utc)
    run_at = body.run_at or now

    task = Task(
        user_id=current_user.id,
        task_type=body.task_type.value,
        payload=body.payload,
        priority=body.priority,
        idempotency_key=idempotency_key,
        max_attempts=body.max_attempts,
        run_at=run_at,
    )
    db.add(task)
    try:
        await db.commit()
        await db.refresh(task)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "DUPLICATE_IDEMPOTENCY_KEY",
                    "message": f"Task with idempotency key '{idempotency_key}' already exists.",
                    "field": "idempotency_key",
                }
            },
        )

    # Publish to RabbitMQ — if this fails, mark task as failed to avoid
    # a dangling 'queued' state with no message.
    try:
        await check_backpressure()
        await publish_task(str(task.id), body.task_type.value)
    except Exception:
        logger.exception("Failed to publish task %s to RabbitMQ", task.id)
        task.status = TaskStatus.FAILED.value
        task.completed_at = datetime.now(timezone.utc)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "code": "QUEUE_UNAVAILABLE",
                    "message": "Task queue is temporarily unavailable. Please retry.",
                    "field": None,
                }
            },
        )

    if idempotency_key:
        await set_idempotency_task_id(
            str(current_user.id), idempotency_key, str(task.id)
        )

    return TaskResponse.model_validate(task)


@router.get("", response_model=TaskListResponse, summary="List tasks")
async def list_tasks(
    current_user: CurrentUser,
    db: DBSession,
    status_filter: TaskStatus | None = Query(None, alias="status"),  # noqa: B008
    task_type_filter: str | None = Query(None, alias="task_type"),
    created_after: datetime | None = Query(None),  # noqa: B008
    created_before: datetime | None = Query(None),  # noqa: B008
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort: str = Query("-created_at", description="Sort field with optional '-' prefix."),
    all_tasks: bool = Query(False, description="Admin-only: include all users' tasks."),
) -> TaskListResponse:
    """List tasks with pagination, filtering, and sorting."""
    is_admin = current_user.role == "admin"
    if not is_admin and all_tasks:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": {
                    "code": "FORBIDDEN",
                    "message": "Only admins can query all tasks.",
                    "field": None,
                }
            },
        )

    base_query = select(Task)
    if not is_admin or not all_tasks:
        base_query = base_query.where(Task.user_id == current_user.id)
    if status_filter:
        base_query = base_query.where(Task.status == status_filter.value)
    if task_type_filter:
        base_query = base_query.where(Task.task_type == task_type_filter)
    if created_after:
        base_query = base_query.where(Task.created_at >= created_after)
    if created_before:
        base_query = base_query.where(Task.created_at <= created_before)

    # Total count
    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Sorting
    sort_field = sort.lstrip("-")
    sort_ascending = not sort.startswith("-")
    column_map = {
        "id": Task.id,
        "status": Task.status,
        "task_type": Task.task_type,
        "created_at": Task.created_at,
        "started_at": Task.started_at,
        "completed_at": Task.completed_at,
    }
    order_col = column_map.get(sort_field, Task.created_at)
    if not sort_ascending:
        base_query = base_query.order_by(order_col.desc())
    else:
        base_query = base_query.order_by(order_col.asc())

    # Pagination
    offset = (page - 1) * page_size
    base_query = base_query.offset(offset).limit(page_size)

    result = await db.execute(base_query)
    tasks = result.scalars().all()

    return TaskListResponse(
        data=[TaskResponse.model_validate(t) for t in tasks],
        pagination=PaginationInfo(page=page, page_size=page_size, total=total),
    )


@router.get("/{task_id}", response_model=TaskResponse, summary="Retrieve a task")
async def get_task(
    task_id: UUID,
    current_user: CurrentUser,
    db: DBSession,
) -> TaskResponse:
    """Get a single task by ID (ownership enforced for non-admins)."""
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "TASK_NOT_FOUND",
                    "message": "Task not found.",
                    "field": None,
                }
            },
        )
    is_admin = current_user.role == "admin"
    if not is_admin and task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "TASK_NOT_FOUND",
                    "message": "Task not found or access denied.",
                    "field": None,
                }
            },
        )
    return TaskResponse.model_validate(task)


@router.post(
    "/{task_id}/cancel",
    response_model=TaskResponse,
    summary="Cancel a task",
)
async def cancel_task(
    task_id: UUID,
    current_user: CurrentUser,
    db: DBSession,
) -> TaskResponse:
    """Cancel a task that is still queued or retrying."""
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "TASK_NOT_FOUND",
                    "message": "Task not found.",
                    "field": None,
                }
            },
        )
    is_admin = current_user.role == "admin"
    if not is_admin and task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "TASK_NOT_FOUND",
                    "message": "Task not found or access denied.",
                    "field": None,
                }
            },
        )
    if task.status not in (TaskStatus.QUEUED.value, TaskStatus.RETRYING.value):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "TASK_NOT_CANCELLABLE",
                    "message": f"Task is in '{task.status}' state and cannot be cancelled.",
                    "field": "status",
                }
            },
        )
    task.status = TaskStatus.CANCELLED.value
    task.completed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(task)
    return TaskResponse.model_validate(task)


@router.post(
    "/{task_id}/retry",
    response_model=TaskResponse,
    summary="Retry a failed or dead-letter task",
)
async def retry_task(
    task_id: UUID,
    current_user: CurrentUser,
    db: DBSession,
) -> TaskResponse:
    """Re-queue a failed or dead-letter task."""
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "TASK_NOT_FOUND",
                    "message": "Task not found.",
                    "field": None,
                }
            },
        )
    is_admin = current_user.role == "admin"
    if not is_admin and task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "TASK_NOT_FOUND",
                    "message": "Task not found or access denied.",
                    "field": None,
                }
            },
        )
    if task.status not in (TaskStatus.FAILED.value, TaskStatus.DEAD_LETTER.value):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "TASK_NOT_RETRYABLE",
                    "message": f"Task is in '{task.status}' state and cannot be retried.",
                    "field": "status",
                }
            },
        )
    task.status = TaskStatus.QUEUED.value
    task.attempt_count = 0
    task.started_at = None
    task.completed_at = None
    task.run_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(task)

    # Re-publish to RabbitMQ
    try:
        await check_backpressure()
        await publish_task(str(task.id), task.task_type)
    except Exception:
        logger.exception("Failed to re-publish retried task %s", task.id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "code": "QUEUE_UNAVAILABLE",
                    "message": "Task queue is temporarily unavailable.",
                    "field": None,
                }
            },
        )
    return TaskResponse.model_validate(task)
