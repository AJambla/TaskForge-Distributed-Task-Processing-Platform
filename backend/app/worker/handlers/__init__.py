"""Task handler registry — maps task_type to async handler functions (IMP-22 SPI)."""
from __future__ import annotations

import functools
import logging
from typing import Any, Callable

logger = logging.getLogger("worker.handlers")

# Internal registry mapping task_type -> handler callable
HANDLER_REGISTRY: dict[str, Callable] = {}
# Registry mapping task_type -> handler metadata (timeout, retries, doc)
HANDLER_METADATA: dict[str, dict[str, Any]] = {}


def register_handler(
    task_type: str,
    timeout_seconds: int = 30,
    max_retries: int = 5,
    description: str | None = None,
) -> Callable:
    """Decorator to register a custom task handler with the TaskForge worker SPI.

    Example:
        @register_handler("pdf_generate", timeout_seconds=60)
        async def handle_pdf(payload: dict) -> dict:
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
        }
        logger.info("Registered task handler for type '%s' (%s)", task_type, fn.__name__)
        return fn

    return decorator


def get_handler(task_type: str) -> Callable:
    """Retrieve the registered handler callable for a task_type."""
    handler = HANDLER_REGISTRY.get(task_type)
    if handler is None:
        raise ValueError(f"Unknown task_type: {task_type!r}")
    return handler


def get_handler_metadata(task_type: str) -> dict[str, Any] | None:
    """Retrieve registered configuration metadata for a task_type."""
    return HANDLER_METADATA.get(task_type)


def list_handlers() -> dict[str, dict[str, Any]]:
    """List all currently registered task handlers and their metadata."""
    return dict(HANDLER_METADATA)


# Register built-in handlers
from app.worker.handlers.email import handle_email_send
from app.worker.handlers.image import handle_image_resize
from app.worker.handlers.webhook import handle_webhook_delivery

register_handler("email_send", timeout_seconds=30, description="Send outbound email")(handle_email_send)
register_handler("image_resize", timeout_seconds=60, description="Resize and optimize image")(handle_image_resize)
register_handler("webhook_delivery", timeout_seconds=30, description="Deliver webhook payload with HMAC")(handle_webhook_delivery)
