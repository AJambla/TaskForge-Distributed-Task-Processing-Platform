"""Unit tests for worker lifecycle workflow integration (FEAT-04)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.models.task import Task
from app.models.task_attempt import TaskAttempt
from app.worker.lifecycle import mark_failure, mark_success


@pytest.mark.asyncio
async def test_mark_success_invokes_workflow_resolution():
    mock_db = AsyncMock()
    task = Task(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        task_type="email_send",
        status="running",
    )
    attempt = TaskAttempt(
        task_id=task.id,
        attempt_number=1,
    )

    with patch("app.core.workflow_engine.resolve_and_dispatch_downstream", new_callable=AsyncMock) as mock_resolve, \
         patch("app.worker.lifecycle.update_worker_stats", new_callable=AsyncMock):

        await mark_success(mock_db, task, attempt, result={"ok": True})
        mock_resolve.assert_called_once_with(mock_db, task.id)


@pytest.mark.asyncio
async def test_mark_failure_terminal_invokes_workflow_failure():
    mock_db = AsyncMock()
    task = Task(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        task_type="email_send",
        status="running",
        attempt_count=3,
        max_attempts=3,
    )
    attempt = TaskAttempt(
        task_id=task.id,
        attempt_number=3,
    )

    with patch("app.core.workflow_engine.handle_step_failure", new_callable=AsyncMock) as mock_fail, \
         patch("app.worker.lifecycle.update_worker_stats", new_callable=AsyncMock):

        await mark_failure(mock_db, task, attempt, outcome="failure", exc=Exception("fatal"))
        mock_fail.assert_called_once_with(mock_db, task.id)
