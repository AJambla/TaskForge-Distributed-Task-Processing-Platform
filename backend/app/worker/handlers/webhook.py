"""Webhook delivery task handler — POSTs to a webhook URL."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings
from app.core.ssrf import validate_url_ssrf_safe

logger = logging.getLogger(__name__)


async def handle_webhook_delivery(payload: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    timeout = settings.task_webhook_timeout_seconds

    url: str | None = payload.get("url") or payload.get("webhook_url")
    if not url:
        raise ValueError("Webhook handler requires 'url' in payload")

    validate_url_ssrf_safe(url)

    body = payload.get("body") or payload.get("payload") or {}
    headers = payload.get("headers", {})
    headers.setdefault("Content-Type", "application/json")

    async with httpx.AsyncClient(
        timeout=timeout,
        headers=headers,
    ) as client:
        resp = await client.post(url, json=body)

    if resp.status_code < 200 or resp.status_code >= 300:
        raise ValueError(
            f"Webhook returned HTTP {resp.status_code}: {resp.text[:500]}"
        )

    response_kb = len(resp.content) / 1024
    if response_kb > settings.webhook_max_response_size_kb:
        logger.warning(
            "Webhook response exceeds %dKB (%.1fKB)",
            settings.webhook_max_response_size_kb,
            response_kb,
        )

    logger.info("Webhook POST to %s succeeded (status=%d)", url, resp.status_code)
    return {"status": "delivered", "http_status": resp.status_code}
