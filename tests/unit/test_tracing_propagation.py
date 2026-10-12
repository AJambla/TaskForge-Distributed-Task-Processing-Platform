"""Unit tests for W3C Distributed Tracing context propagation (IMP-20)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.core.tracing import (
    extract_trace_context,
    generate_span_id,
    generate_trace_id,
    parse_traceparent,
)
from app.models.task import Task
from app.worker.main import consume_task


def test_generate_trace_and_span_ids():
    trace_id = generate_trace_id()
    span_id = generate_span_id()
    assert len(trace_id) == 32
    assert len(span_id) == 16
    assert int(trace_id, 16) > 0
    assert int(span_id, 16) > 0


def test_parse_valid_traceparent():
    tp = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    trace_id, parent_id, is_sampled = parse_traceparent(tp)
    assert trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert parent_id == "00f067aa0ba902b7"
    assert is_sampled is True


def test_parse_invalid_traceparent():
    assert parse_traceparent(None) == (None, None, False)
    assert parse_traceparent("") == (None, None, False)
    # Invalid length
    assert parse_traceparent("00-1234-5678-01") == (None, None, False)
    # All zeros
    assert parse_traceparent("00-00000000000000000000000000000000-00f067aa0ba902b7-01") == (None, None, False)


def test_extract_trace_context_from_headers():
    valid_tp = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    trace_id, child_span = extract_trace_context({"traceparent": valid_tp})
    assert trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert len(child_span) == 16
    assert child_span != "00f067aa0ba902b7"


@pytest.mark.asyncio
async def test_consume_task_with_traceparent():
    mock_db = AsyncMock()
    task_id = uuid.uuid4()
    task = Task(
        id=task_id,
        user_id=uuid.uuid4(),
        task_type="email_send",
        status="queued",
        priority=0,
        max_attempts=3,
        attempt_count=0,
        created_at=datetime.now(timezone.utc),
        payload={"to": "test@example.com"},
    )
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = task
    mock_db.execute.return_value = mock_res

    tp = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    with patch("app.worker.main.get_handler") as mock_handler:
        mock_fn = AsyncMock(return_value={"status": "sent"})
        mock_handler.return_value = mock_fn
        status, attempts, max_att, defer = await consume_task(
            mock_db, str(task_id), "email_send", traceparent=tp
        )
        assert status == "succeeded"
        assert attempts == 1
