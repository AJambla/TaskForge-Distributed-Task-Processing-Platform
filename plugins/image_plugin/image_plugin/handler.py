"""TaskForge image processing plugin example (FEAT-06).

Implements the image_resize handler using the public TaskForge Handler SDK:
- @register_handler decorator
- TaskContext (progress reporting, artifact upload)
- Pydantic schema validation
"""
from __future__ import annotations

import base64
import io
import logging
from typing import Any
import uuid

import httpx
from PIL import Image
from pydantic import BaseModel, Field

from app.worker.context import TaskContext
from app.worker.handlers import register_handler

logger = logging.getLogger("plugins.image_plugin")


class ImageResizePayload(BaseModel):
    """Payload schema for image_resize task."""
    source_url: str | None = Field(None, description="URL of the source image to resize.")
    data: str | None = Field(None, description="Optional base64 encoded data URI.")
    width: int = Field(800, gt=0, description="Target bounding box width.")
    height: int = Field(600, gt=0, description="Target bounding box height.")


def _resize_sync(image_bytes: bytes, max_width: int, max_height: int) -> tuple[bytes, str]:
    stream = io.BytesIO(image_bytes)
    img = Image.open(stream)
    img = img.convert("RGB") if img.mode == "RGBA" else img
    img.thumbnail((max_width, max_height))

    buf = io.BytesIO()
    fmt = "JPEG" if img.mode in ("RGB", "L") else "PNG"
    img.save(buf, format=fmt)
    return buf.getvalue(), fmt


@register_handler("image_resize", timeout_seconds=60, schema=ImageResizePayload, description="Resize and optimize image")
async def handle_image_resize(payload: dict[str, Any], ctx: TaskContext) -> dict[str, Any]:
    """Download, resize image, and upload thumbnail as a TaskForge artifact."""
    source_url = payload.get("source_url") or payload.get("url")
    data_uri = payload.get("data")
    max_w = int(payload.get("width", 800))
    max_h = int(payload.get("height", 600))

    await ctx.set_progress(10, "Fetching image data")

    if data_uri and data_uri.startswith("data:"):
        _, b64_part = data_uri.split(",", 1)
        image_bytes = base64.b64decode(b64_part)
    elif source_url:
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            resp = await client.get(source_url)
            resp.raise_for_status()
            image_bytes = resp.content
    else:
        raise ValueError("Image resize requires 'source_url' or 'data'")

    await ctx.set_progress(50, "Resizing image")
    resized_bytes, fmt = _resize_sync(image_bytes, max_w, max_h)

    await ctx.set_progress(80, "Uploading artifact")
    ext = fmt.lower()
    filename = f"resized_{uuid.uuid4().hex[:8]}.{ext}"
    content_type = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"

    artifact_meta = await ctx.upload_artifact(
        filename=filename,
        data=resized_bytes,
        content_type=content_type,
    )

    await ctx.set_progress(100, "Done")

    return {
        "format": fmt,
        "size_bytes": len(resized_bytes),
        "artifacts": [artifact_meta],
    }
