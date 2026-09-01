"""Email task handler — sends emails via SMTP."""
from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)


def _send_email_sync(payload: dict[str, Any]) -> None:
    settings = get_settings()

    msg = EmailMessage()
    msg["Subject"] = payload["subject"]
    msg["From"] = settings.smtp_from
    msg["To"] = payload["to"]
    msg.set_content(payload.get("body", ""))

    if payload.get("html"):
        msg.add_alternative(payload["html"], subtype="html")

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
        server.starttls()
        if settings.smtp_user and settings.smtp_password:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)


async def handle_email_send(payload: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    timeout = settings.task_email_timeout_seconds

    await asyncio.wait_for(
        asyncio.to_thread(_send_email_sync, payload),
        timeout=timeout,
    )

    logger.info("Email sent to %s", payload.get("to"))
    return {"status": "sent", "to": payload.get("to")}
