"""Image resize task handler — downloads an image and resizes it."""
from __future__ import annotations

import asyncio
import base64
import io
import logging
from typing import Any

import httpx
from PIL import Image

from app.config import get_settings

logger = logging.getLogger(__name__)

SUPPORTED_FORMATS = ("PNG", "JPEG", "WEBP")


def _resize_image_sync(
    image_bytes: bytes,
    max_dimension: int,
) -> tuple[bytes, str]:
    img = Image.open(io.BytesIO(image_bytes))
    img = img.convert("RGB") if img.mode == "RGBA" else img

    if img.width > max_dimension or img.height > max_dimension:
        img.thumbnail((max_dimension, max_dimension), Image.LANCZOS)

    buf = io.BytesIO()
    fmt = "JPEG" if img.mode in ("RGB", "L") else img.format or "PNG"
    img.save(buf, format=fmt)
    resized_bytes = buf.getvalue()
    return resized_bytes, fmt


async def handle_image_resize(payload: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    max_dim = settings.image_max_dimension_px
    timeout = settings.task_image_resize_timeout_seconds

    source: str | None = payload.get("url") or payload.get("source_url")
    data: str | None = payload.get("data")

    if not source and not data:
        raise ValueError("Image handler requires 'url' or 'data' in payload")

    if data and data.startswith("data:"):
        mime_part, b64_part = data.split(",", 1)
        fmt = mime_part.split("/")[1].split(";")[0].upper()
        image_bytes = base64.b64decode(b64_part)
    elif source:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(source)
            resp.raise_for_status()
            image_bytes = resp.content
    else:
        raise ValueError("Invalid image source")

    resized_bytes, fmt = await asyncio.wait_for(
        asyncio.to_thread(_resize_image_sync, image_bytes, max_dim),
        timeout=timeout,
    )

    result_size_mb = len(resized_bytes) / (1024 * 1024)
    if result_size_mb > settings.image_max_response_size_mb:
        raise ValueError(
            f"Resized image exceeds {settings.image_max_response_size_mb}MB limit"
        )

    logger.info("Image resized: %sx%s -> %s", fmt, len(resized_bytes), result_size_mb)
    return {
        "format": fmt,
        "size_bytes": len(resized_bytes),
        "size_mb": round(result_size_mb, 3),
    }
