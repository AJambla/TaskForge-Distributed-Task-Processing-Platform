"""Unit tests for Pluggable Handler SDK, TaskContext and Entry Point Discovery (FEAT-06)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from pydantic import BaseModel, Field

from app.worker.context import TaskContext
from app.worker.handlers import (
    HANDLER_REGISTRY,
    get_handler,
    get_handler_metadata,
    get_handler_schema,
    handler,
    register_handler,
)


class CustomReportPayload(BaseModel):
    report_id: str = Field(...)
    format: str = Field(default="pdf")


def test_register_handler_with_schema_and_metadata():
    """Verify @register_handler stores handler, schema, and metadata properly."""
    @register_handler(
        task_type="generate_report",
        timeout_seconds=45,
        max_retries=3,
        schema=CustomReportPayload,
        description="Generates executive PDF report",
    )
    async def sample_report_handler(payload: dict, ctx: TaskContext) -> dict:
        return {"ok": True}

    assert "generate_report" in HANDLER_REGISTRY
    assert get_handler("generate_report") is sample_report_handler

    meta = get_handler_metadata("generate_report")
    assert meta is not None
    assert meta["timeout_seconds"] == 45
    assert meta["max_retries"] == 3
    assert meta["description"] == "Generates executive PDF report"
    assert meta["has_context"] is True
    assert meta["schema_name"] == "CustomReportPayload"

    assert get_handler_schema("generate_report") is CustomReportPayload


def test_handler_alias_decorator():
    """Verify @handler functions as an alias to @register_handler."""
    @handler("quick_ping", timeout_seconds=10)
    async def ping_handler(payload: dict) -> dict:
        return {"pong": True}

    assert get_handler("quick_ping") is ping_handler
    meta = get_handler_metadata("quick_ping")
    assert meta["timeout_seconds"] == 10
    assert meta["has_context"] is False



@pytest.mark.asyncio
async def test_task_context_set_progress():
    """Verify TaskContext sets progress via Redis."""
    ctx = TaskContext(
        task_id="123e4567-e89b-12d3-a456-426614174000",
        task_type="custom_task",
        attempt=2,
        worker_id="worker-test",
        trace_id="4bf92f3577b34da6a3ce929d0e0e4736",
    )
    assert ctx.task_id == "123e4567-e89b-12d3-a456-426614174000"
    assert ctx.attempt == 2

    with patch("app.worker.context.get_redis", AsyncMock()) as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        await ctx.set_progress(75, "Processing batches")
        assert mock_redis.publish.called

