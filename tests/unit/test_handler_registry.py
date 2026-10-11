"""Unit tests for pluggable task handler registry SPI (IMP-22)."""
from __future__ import annotations

import pytest
from app.worker.executor import get_timeout
from app.worker.handlers import (
    HANDLER_REGISTRY,
    get_handler,
    get_handler_metadata,
    list_handlers,
    register_handler,
)


def test_builtin_handlers_registered():
    handlers = list_handlers()
    assert "email_send" in handlers
    assert "webhook_delivery" in handlers

    assert callable(get_handler("email_send"))
    assert callable(get_handler("webhook_delivery"))


def test_register_custom_handler_decorator():
    @register_handler("report_pdf", timeout_seconds=90, max_retries=2, description="Generate PDF invoice")
    async def handle_pdf(payload: dict) -> dict:
        return {"pdf_url": "s3://invoices/123.pdf"}

    assert "report_pdf" in list_handlers()
    fn = get_handler("report_pdf")
    assert fn == handle_pdf

    meta = get_handler_metadata("report_pdf")
    assert meta is not None
    assert meta["timeout_seconds"] == 90
    assert meta["max_retries"] == 2
    assert meta["description"] == "Generate PDF invoice"

    assert get_timeout("report_pdf") == 90


def test_get_unknown_handler_raises_value_error():
    with pytest.raises(ValueError, match="Unknown task_type: 'non_existent'"):
        get_handler("non_existent")
