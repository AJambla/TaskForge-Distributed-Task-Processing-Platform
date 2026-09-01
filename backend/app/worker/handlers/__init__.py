"""Task handler registry — maps task_type to async handler functions."""
from __future__ import annotations

from app.worker.handlers.email import handle_email_send
from app.worker.handlers.image import handle_image_resize
from app.worker.handlers.webhook import handle_webhook_delivery

HANDLER_REGISTRY: dict[str, object] = {
    "email_send": handle_email_send,
    "image_resize": handle_image_resize,
    "webhook_delivery": handle_webhook_delivery,
}


def get_handler(task_type: str):
    handler = HANDLER_REGISTRY.get(task_type)
    if handler is None:
        raise ValueError(f"Unknown task_type: {task_type!r}")
    return handler  # type: ignore[return-value]
