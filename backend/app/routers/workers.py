"""Worker router — list workers, view worker detail with recent attempts.

Read endpoints are available to any authenticated user: worker health is
shared platform visibility.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.core.deps import CurrentUser, DBSession
from app.models.worker_registration import WorkerRegistration
from app.schemas.workers import TaskAttemptResponse, WorkerDetail, WorkerListItem

logger = logging.getLogger(__name__)

router = APIRouter()


async def _mark_stale_workers_offline(db) -> None:
    """Workers that stopped heartbeating are offline, whatever they claim."""
    cutoff = datetime.now(timezone.utc) - timedelta(
        seconds=get_settings().worker_heartbeat_timeout_seconds
    )
    await db.execute(
        update(WorkerRegistration)
        .where(
            WorkerRegistration.status == "online",
            WorkerRegistration.last_heartbeat_at < cutoff,
        )
        .values(
            status="offline",
            # Self-assignment suppresses onupdate=func.now() so the stored
            # heartbeat still shows when the worker was actually last seen.
            last_heartbeat_at=WorkerRegistration.last_heartbeat_at,
        )
    )
    await db.commit()


@router.get(
    "",
    response_model=list[WorkerListItem],
    summary="List all workers",
)
async def list_workers(
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> list[WorkerListItem]:
    """List all worker registrations, sorted by last heartbeat descending."""
    await _mark_stale_workers_offline(db)
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
    current_user: CurrentUser,
    db: DBSession,
    limit: int = Query(10, ge=1, le=50, description="Number of recent attempts."),
) -> WorkerDetail:
    """Get a single worker's detail including its recent task attempts."""
    result = await db.execute(
        select(WorkerRegistration)
        .where(WorkerRegistration.id == worker_id)
        .options(selectinload(WorkerRegistration.attempts))
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
