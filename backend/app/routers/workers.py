"""Worker admin router — list workers, view worker detail with recent attempts.

Admin-only endpoints per Phase 8 spec.
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.core.deps import AdminUser, DBSession
from app.models.task_attempt import TaskAttempt
from app.models.worker_registration import WorkerRegistration
from app.schemas.workers import TaskAttemptResponse, WorkerDetail, WorkerListItem

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "",
    response_model=list[WorkerListItem],
    summary="List all workers",
)
async def list_workers(
    admin: AdminUser,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> list[WorkerListItem]:
    """List all worker registrations, sorted by last heartbeat descending."""
    offset = (page - 1) * page_size
    result = await db.execute(
        select(WorkerRegistration)
        .order_by(WorkerRegistration.last_heartbeat_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    workers = result.scalars().all()
    return [WorkerListItem.model_validate(w) for w in workers]


@router.get(
    "/{worker_id}",
    response_model=WorkerDetail,
    summary="Get worker detail with recent attempts",
)
async def get_worker(
    worker_id: UUID,
    admin: AdminUser,
    db: DBSession,
    limit: int = Query(10, ge=1, le=50, description="Number of recent attempts."),
) -> WorkerDetail:
    """Get a single worker's detail including its recent task attempts."""
    result = await db.execute(
        select(WorkerRegistration)
        .where(WorkerRegistration.id == worker_id)
        .options(joinedload(WorkerRegistration.attempts))
    )
    worker = result.scalar_one_or_none()
    if not worker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "WORKER_NOT_FOUND",
                    "message": "Worker not found.",
                    "field": None,
                }
            },
        )

    recent = sorted(
        worker.attempts,
        key=lambda a: a.attempt_number,
        reverse=True,
    )[:limit]

    return WorkerDetail(
        id=worker.id,
        hostname=worker.hostname,
        status=worker.status,
        concurrency_limit=worker.concurrency_limit,
        current_task_count=worker.current_task_count,
        last_heartbeat_at=worker.last_heartbeat_at,
        tasks_processed=worker.tasks_processed,
        tasks_failed=worker.tasks_failed,
        registered_at=worker.registered_at,
        recent_attempts=[TaskAttemptResponse.model_validate(a) for a in recent],
    )
