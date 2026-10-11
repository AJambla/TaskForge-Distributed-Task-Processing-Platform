"""Task router — submit, list, retrieve, cancel, and retry tasks.

Per API.md:
- POST   /api/v1/tasks          — create (with idempotency)
- GET    /api/v1/tasks          — list (paginated, filterable, sortable)
- GET    /api/v1/tasks/{id}     — retrieve single task
- POST   /api/v1/tasks/{id}/cancel — cancel a queued/retrying task
- POST   /api/v1/tasks/{id}/retry  — re-queue a failed/dead_letter task
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.core.deps import CurrentUser, DBSession
from app.core.rabbitmq import check_backpressure, publish_task
from app.core.rate_limit import make_rate_limiter
from app.core.redis import check_idempotency, set_idempotency_task_id
from app.models.artifact import Artifact
from app.models.task import Task
from app.schemas.artifacts import (
    ArtifactItemResponse,
    DownloadUrlResponse,
    TaskResultResponse,
)
from app.schemas.tasks import (
    PaginationInfo,
    TaskBulkCreateRequest,
    TaskBulkResponse,
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
    rate_limit: Annotated[None, Depends(make_rate_limiter(get_settings().rate_limit_task_submission_per_minute))],
    response: Response = None,
    idempotency_key_header: Annotated[
        str | None,
        Header(alias="Idempotency-Key", description="Unique request idempotency key."),
    ] = None,
    idempotency_key_query: str | None = Query(
        None,
        alias="Idempotency-Key",
        description="Alternative query idempotency key for backward compatibility.",
    ),
    traceparent_header: Annotated[
        str | None,
        Header(alias="traceparent", description="W3C Trace Context traceparent header (IMP-20)."),
    ] = None,
) -> TaskResponse:
    """Submit a task for processing with idempotency protection."""
    # Reject while backpressuring, before any state is written, so a 429
    # never leaves a queued task row with no queued message.
    await check_backpressure()

    from app.core.tracing import (
        create_traceparent,
        extract_context_from_carrier,
        get_current_trace_id,
        inject_carrier,
        parse_traceparent,
    )
    # Determine W3C trace context: check active OpenTelemetry span first, then inbound header
    active_trace_id = get_current_trace_id()
    if active_trace_id:
        carrier = inject_carrier()
        traceparent = carrier.get("traceparent") or create_traceparent(trace_id=active_trace_id)
        task_trace_id = active_trace_id
    elif traceparent_header:
        traceparent = traceparent_header
        t_id, _, _ = parse_traceparent(traceparent)
        task_trace_id = t_id or create_traceparent().split("-")[1]
    else:
        traceparent = create_traceparent()
        task_trace_id = traceparent.split("-")[1]

    if response:
        response.headers["traceparent"] = traceparent

    idempotency_key = idempotency_key_header or idempotency_key_query or body.idempotency_key

    if idempotency_key:
        already = await check_idempotency(
            str(current_user.id), idempotency_key
        )
        if already:
            existing_result = await db.execute(
                select(Task).where(
                    Task.user_id == current_user.id,
                    Task.idempotency_key == idempotency_key,
                )
            )
            existing_task = existing_result.scalar_one_or_none()
            if existing_task:
                if response:
                    response.headers["Idempotent-Replayed"] = "true"
                return TaskResponse.from_task(existing_task)
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
    run_at = body.run_at
    if body.recurrence_rule and not run_at:
        from croniter import croniter
        run_at = croniter(body.recurrence_rule, now).get_next(datetime)
        if run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=timezone.utc)
    if not run_at:
        run_at = now

    task_type_str = body.task_type.value if hasattr(body.task_type, "value") else str(body.task_type)
    task = Task(
        user_id=current_user.id,
        task_type=task_type_str,
        payload=body.payload,
        priority=body.priority,
        idempotency_key=idempotency_key,
        max_attempts=body.max_attempts,
        run_at=run_at,
        recurrence_rule=body.recurrence_rule,
        trace_id=task_trace_id,
    )
    db.add(task)
    await db.flush()

    should_publish = not (body.recurrence_rule and run_at > now)
    outbox_entry = None
    if should_publish:
        from app.models.task_outbox import TaskOutbox
        outbox_entry = TaskOutbox(
            task_id=task.id,
            task_type=task.task_type,
            payload=task.payload,
            priority=task.priority,
            traceparent=traceparent,
            status="pending",
        )
        db.add(outbox_entry)

    try:
        await db.commit()
        await db.refresh(task)
    except IntegrityError:
        await db.rollback()
        existing_result = await db.execute(
            select(Task).where(
                Task.user_id == current_user.id,
                Task.idempotency_key == idempotency_key,
            )
        )
        existing_task = existing_result.scalar_one_or_none()
        if existing_task:
            if response:
                response.headers["Idempotent-Replayed"] = "true"
            return TaskResponse.model_validate(existing_task)
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

    # For future recurring tasks, let the scheduler dispatch at run_at.
    # Otherwise publish immediately (worker handles immediate or delayed retry-parking).
    if should_publish and outbox_entry is not None:
        try:
            await publish_task(
                str(task.id),
                body.task_type.value,
                priority=body.priority,
                traceparent=traceparent,
            )
            outbox_entry.status = "published"
            outbox_entry.processed_at = datetime.now(timezone.utc)
            await db.commit()
        except Exception:
            logger.warning(
                "Immediate publish failed for task %s; outbox relay will retry asynchronously.",
                task.id,
            )

    if idempotency_key:
        await set_idempotency_task_id(
            str(current_user.id), idempotency_key, str(task.id)
        )

    return TaskResponse.from_task(task)


@router.post(
    "/bulk",
    response_model=TaskBulkResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit multiple tasks in a single batch (IMP-17)",
)
async def create_tasks_bulk(
    body: TaskBulkCreateRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> TaskBulkResponse:
    """Submit a batch of up to 1,000 tasks atomically."""
    await check_backpressure()

    now = datetime.now(timezone.utc)
    from app.models.task_outbox import TaskOutbox

    created_tasks: list[Task] = []
    outbox_entries: list[TaskOutbox] = []
    from app.core.tracing import create_traceparent, get_current_trace_id
    active_trace_id = get_current_trace_id()
    bulk_trace_id = active_trace_id or create_traceparent().split("-")[1]
    bulk_traceparent = create_traceparent(trace_id=bulk_trace_id)

    for req in body.tasks:
        run_at = req.run_at or now
        task_type_str = req.task_type.value if hasattr(req.task_type, "value") else str(req.task_type)
        task = Task(
            user_id=current_user.id,
            task_type=task_type_str,
            payload=req.payload,
            priority=req.priority,
            idempotency_key=req.idempotency_key,
            max_attempts=req.max_attempts,
            run_at=run_at,
            recurrence_rule=req.recurrence_rule,
            trace_id=bulk_trace_id,
        )
        db.add(task)
        created_tasks.append(task)

    await db.flush()

    for task in created_tasks:
        should_publish = not (task.recurrence_rule and task.run_at > now)
        if should_publish:
            outbox_entry = TaskOutbox(
                task_id=task.id,
                task_type=task.task_type,
                payload=task.payload,
                priority=task.priority,
                traceparent=bulk_traceparent,
                status="pending",
            )
            db.add(outbox_entry)
            outbox_entries.append(outbox_entry)

    await db.commit()

    # Best-effort immediate publication
    for task, outbox_entry in zip(created_tasks, outbox_entries):
        try:
            await publish_task(
                str(task.id),
                task.task_type,
                priority=task.priority,
                traceparent=bulk_traceparent,
            )
            outbox_entry.status = "published"
            outbox_entry.processed_at = datetime.now(timezone.utc)
        except Exception:
            logger.warning("Bulk immediate publish failed for task %s; outbox relay will drain.", task.id)

    await db.commit()

    return TaskBulkResponse(
        submitted_count=len(created_tasks),
        tasks=[TaskResponse.from_task(t) for t in created_tasks],
    )


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
    cursor: str | None = Query(None, description="Keyset pagination cursor token (IMP-18)."),
    sort: str = Query("-created_at", description="Sort field with optional '-' prefix."),
    all_tasks: bool = Query(False, description="Admin-only: include all users' tasks."),
) -> TaskListResponse:
    """List tasks with pagination, filtering, and sorting."""
    import base64
    import json

    from fastapi.params import Query as QueryParam

    # Normalize defaults when invoked directly as a Python callable in tests
    if isinstance(status_filter, QueryParam):
        status_filter = status_filter.default
    if isinstance(task_type_filter, QueryParam):
        task_type_filter = task_type_filter.default
    if isinstance(created_after, QueryParam):
        created_after = created_after.default
    if isinstance(created_before, QueryParam):
        created_before = created_before.default
    if isinstance(page, QueryParam):
        page = page.default
    if isinstance(page_size, QueryParam):
        page_size = page_size.default
    if isinstance(cursor, QueryParam):
        cursor = cursor.default
    if isinstance(sort, QueryParam):
        sort = sort.default
    if isinstance(all_tasks, QueryParam):
        all_tasks = all_tasks.default

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
        val = status_filter.value if hasattr(status_filter, "value") else str(status_filter)
        base_query = base_query.where(Task.status == val)
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

    # Cursor-based keyset filter (IMP-18)
    if cursor:
        try:
            decoded = json.loads(base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8"))
            cursor_dt = datetime.fromisoformat(decoded["created_at"])
            cursor_id = UUID(decoded["id"])
            # Default sort is -created_at: where created_at < cursor_dt or (created_at == cursor_dt and id < cursor_id)
            base_query = base_query.where(
                (Task.created_at < cursor_dt) |
                ((Task.created_at == cursor_dt) & (Task.id < cursor_id))
            )
        except Exception as exc:
            logger.warning("Invalid pagination cursor: %s", exc)

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
        base_query = base_query.order_by(order_col.desc(), Task.id.desc())
    else:
        base_query = base_query.order_by(order_col.asc(), Task.id.asc())

    # Pagination: if cursor is provided, skip offset for O(1) performance
    if not cursor:
        offset = (page - 1) * page_size
        base_query = base_query.offset(offset)
    base_query = base_query.limit(page_size)

    result = await db.execute(base_query)
    tasks = result.scalars().all()

    # Compute next_cursor
    next_cursor = None
    if len(tasks) == page_size:
        last_task = tasks[-1]
        raw_cursor = json.dumps({
            "created_at": last_task.created_at.isoformat() if last_task.created_at else now.isoformat(),
            "id": str(last_task.id),
        })
        next_cursor = base64.urlsafe_b64encode(raw_cursor.encode("utf-8")).decode("utf-8")

    return TaskListResponse(
        data=[TaskResponse.from_task(t) for t in tasks],
        pagination=PaginationInfo(page=page, page_size=page_size, total=total, next_cursor=next_cursor),
    )


async def get_task_with_artifacts(task_id: UUID, db: AsyncSession) -> Task | None:
    """Helper to fetch task with joined artifacts."""
    from sqlalchemy.orm import selectinload
    stmt = select(Task).where(Task.id == task_id).options(selectinload(Task.artifacts))
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


@router.get("/{task_id}/result", response_model=TaskResultResponse, summary="Retrieve structured task results and artifacts")
async def get_task_result(
    task_id: UUID,
    current_user: CurrentUser,
    db: DBSession,
) -> TaskResultResponse:
    """Retrieve execution result and associated artifacts (ownership enforced)."""
    task = await get_task_with_artifacts(task_id, db)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "TASK_NOT_FOUND", "message": "Task not found.", "field": None}},
        )
    is_admin = current_user.role == "admin"
    if not is_admin and task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "TASK_NOT_FOUND", "message": "Task not found or access denied.", "field": None}},
        )

    artifacts = [
        ArtifactItemResponse.model_validate(art) for art in (task.artifacts or [])
    ]
    return TaskResultResponse(
        task_id=task.id,
        status=task.status,
        result=task.result,
        artifacts=artifacts,
    )


@router.get("/{task_id}/download", response_model=DownloadUrlResponse, summary="Generate signed download URL for task artifact")
async def get_task_download_url(
    task_id: UUID,
    current_user: CurrentUser,
    db: DBSession,
    artifact_id: UUID | None = Query(None, description="Specific artifact ID to download"),
) -> DownloadUrlResponse:
    """Generate temporary signed download URL for task artifact."""
    task = await get_task_with_artifacts(task_id, db)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "TASK_NOT_FOUND", "message": "Task not found.", "field": None}},
        )
    is_admin = current_user.role == "admin"
    if not is_admin and task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "TASK_NOT_FOUND", "message": "Task not found or access denied.", "field": None}},
        )

    task_artifacts = task.artifacts or []
    if not task_artifacts:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "ARTIFACT_NOT_FOUND", "message": "No artifacts available for this task.", "field": None}},
        )

    target_art: Artifact | None = None
    if artifact_id:
        for art in task_artifacts:
            if art.id == artifact_id:
                target_art = art
                break
        if not target_art:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": {"code": "ARTIFACT_NOT_FOUND", "message": f"Artifact {artifact_id} not found on task.", "field": None}},
            )
    else:
        target_art = task_artifacts[0]

    from app.core.storage import get_storage_backend
    storage = get_storage_backend()
    expires_in = 900
    download_url = storage.generate_download_url(
        target_art.storage_key, filename=target_art.filename, expires_in=expires_in
    )

    return DownloadUrlResponse(
        artifact_id=target_art.id,
        filename=target_art.filename,
        download_url=download_url,
        expires_in=expires_in,
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
    return TaskResponse.from_task(task)


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
    return TaskResponse.from_task(task)


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
    # Backpressure check before any mutation: a 429 must leave the task
    # in its retryable state, not flip it to queued with no message.
    await check_backpressure()

    prev_status = task.status
    prev_attempt_count = task.attempt_count
    prev_completed_at = task.completed_at

    task.status = TaskStatus.QUEUED.value
    task.attempt_count = 0
    task.started_at = None
    task.completed_at = None
    task.run_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(task)

    # Re-publish to RabbitMQ
    try:
        await publish_task(str(task.id), task.task_type, priority=task.priority)
    except Exception:
        logger.exception("Failed to re-publish retried task %s", task.id)
        # Roll the row back to its retryable state — leaving it 'queued'
        # with no message anywhere would strand it forever.
        task.status = prev_status
        task.attempt_count = prev_attempt_count
        task.completed_at = prev_completed_at
        await db.commit()
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
    return TaskResponse.from_task(task)


@router.get("/{task_id}/events", summary="Stream task state changes via SSE (IMP-19)")
async def stream_task_events(
    task_id: UUID,
    current_user: CurrentUser,
    db: DBSession,
):
    """Stream real-time task lifecycle updates using Server-Sent Events (SSE)."""
    from fastapi.responses import StreamingResponse
    from app.core.redis import get_redis

    is_admin = current_user.role == "admin"
    query = select(Task).where(Task.id == task_id)
    if not is_admin:
        query = query.where(Task.user_id == current_user.id)
    result = await db.execute(query)
    task = result.scalar_one_or_none()

    if not task:
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

    async def event_generator():
        # Yield initial current status immediately
        initial_data = json.dumps({
            "task_id": str(task.id),
            "status": task.status,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "result": task.result,
        })
        yield f"data: {initial_data}\n\n"

        # If already terminal, close stream
        if task.status in ("succeeded", "failed", "dead_letter"):
            return

        redis_client = await get_redis()
        pubsub = redis_client.pubsub()
        channel_name = f"task:events:{task.id}"
        await pubsub.subscribe(channel_name)

        try:
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message.get("type") == "message":
                    payload = message.get("data")
                    yield f"data: {payload}\n\n"
                    # Check if terminal status reached to gracefully close
                    try:
                        data_dict = json.loads(payload)
                        if data_dict.get("status") in ("succeeded", "failed", "dead_letter"):
                            break
                    except Exception:
                        pass
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe(channel_name)
            await pubsub.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/handlers",
    summary="List all registered task handlers and metadata (FEAT-06)",
    tags=["tasks"],
)
async def get_registered_handlers() -> dict[str, Any]:
    """Retrieve all discovered and registered task handlers with their configuration."""
    from app.worker.handlers import list_handlers
    return {"handlers": list_handlers()}


