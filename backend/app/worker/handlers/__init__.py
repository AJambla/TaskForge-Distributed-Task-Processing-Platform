"""Task handler registry and pluggable SPI (FEAT-06 & IMP-22).

Supports:
- `@register_handler` and `@handler` decorator with optional Pydantic schema validation
- In-memory handler function and metadata storage
- Dynamic plugin discovery via `importlib.metadata.entry_points(group="taskforge.handlers")`
- `TaskContext` re-export for handler authors
"""
from __future__ import annotations

import inspect
import logging
from typing import Any, Callable, Type

from pydantic import BaseModel

from app.worker.context import TaskContext

logger = logging.getLogger("worker.handlers")

# Internal registry mapping task_type -> handler callable
HANDLER_REGISTRY: dict[str, Callable] = {}
# Registry mapping task_type -> handler metadata (timeout, retries, doc, schema)
HANDLER_METADATA: dict[str, dict[str, Any]] = {}
# Registry mapping task_type -> Pydantic payload model
SCHEMA_REGISTRY: dict[str, Type[BaseModel]] = {}


def register_handler(
    task_type: str,
    timeout_seconds: int = 30,
    max_retries: int = 5,
    schema: Type[BaseModel] | None = None,
    description: str | None = None,
) -> Callable:
    """Decorator to register a task handler with the TaskForge worker SPI.

    Example:
        @register_handler("generate_invoice_pdf", timeout_seconds=60, schema=InvoicePayload)
        async def handle_invoice(payload: dict, ctx: TaskContext) -> dict:
            ...
    """
    def decorator(fn: Callable) -> Callable:
        HANDLER_REGISTRY[task_type] = fn
        HANDLER_METADATA[task_type] = {
            "task_type": task_type,
            "timeout_seconds": timeout_seconds,
            "max_retries": max_retries,
            "description": description or fn.__doc__,
            "handler_name": fn.__name__,
            "has_context": _handler_accepts_context(fn),
        }
        if schema is not None:
            SCHEMA_REGISTRY[task_type] = schema
            HANDLER_METADATA[task_type]["schema_name"] = schema.__name__

        logger.info("Registered task handler for type '%s' (%s)", task_type, fn.__name__)
        return fn

    return decorator


# Alias for concise developer ergonomics: @handler(...)
handler = register_handler


def _handler_accepts_context(fn: Callable) -> bool:
    """Check if handler expects a TaskContext argument."""
    try:
        sig = inspect.signature(fn)
        params = list(sig.parameters.values())
        if len(params) >= 2:
            return True
        for p in params:
            if p.name in ("ctx", "context") or p.annotation is TaskContext:
                return True
    except Exception:
        pass
    return False


def get_handler(task_type: str) -> Callable:
    """Retrieve the registered handler callable for a task_type."""
    h = HANDLER_REGISTRY.get(task_type)
    if h is None:
        raise ValueError(f"Unknown task_type: {task_type!r}")
    return h


def get_handler_metadata(task_type: str) -> dict[str, Any] | None:
    """Retrieve registered configuration metadata for a task_type."""
    return HANDLER_METADATA.get(task_type)


def get_handler_schema(task_type: str) -> Type[BaseModel] | None:
    """Retrieve registered Pydantic schema model for a task_type if one was registered."""
    return SCHEMA_REGISTRY.get(task_type)


def list_handlers() -> dict[str, dict[str, Any]]:
    """List all currently registered task handlers and their metadata."""
    return dict(HANDLER_METADATA)


# Register built-in handlers
from app.worker.handlers.email import handle_email_send  # noqa: E402
from app.worker.handlers.webhook import handle_webhook_delivery  # noqa: E402

register_handler("email_send", timeout_seconds=30, description="Send outbound email")(handle_email_send)
register_handler("webhook_delivery", timeout_seconds=30, description="Deliver webhook payload with HMAC")(handle_webhook_delivery)

