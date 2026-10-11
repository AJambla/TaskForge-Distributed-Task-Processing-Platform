"""Image resize task handler — downloads an image and resizes it."""
from __future__ import annotations

import asyncio
import base64
import io
import logging
from pathlib import Path
from typing import Any
import uuid

import httpx
from PIL import Image

from app.config import get_settings
from app.core.ssrf import validate_url_ssrf_safe

logger = logging.getLogger(__name__)

SUPPORTED_FORMATS = ("PNG", "JPEG", "WEBP")


def _resize_image_sync(
    image_bytes: bytes,
    max_dimension: int,
) -> tuple[bytes, str]:
    stream = io.BytesIO(image_bytes)
    img = Image.open(stream)

    # Use draft downsampling on JPEG images before full decode
    if getattr(img, "format", None) == "JPEG" and (img.width > max_dimension * 2 or img.height > max_dimension * 2):
        try:
            img.draft("RGB", (max_dimension * 2, max_dimension * 2))
        except Exception:
            pass

    img = img.convert("RGB") if img.mode == "RGBA" else img

    if img.width > max_dimension or img.height > max_dimension:
        # Fast BOX pre-downscale if image is more than 3x target size, then final high-quality Lanczos
        ratio = max(img.width / max_dimension, img.height / max_dimension)
        if ratio > 3.0:
            intermediate_size = (int(img.width / (ratio / 2)), int(img.height / (ratio / 2)))
            img = img.resize(intermediate_size, Image.BOX)
        img.thumbnail((max_dimension, max_dimension), Image.LANCZOS)

    buf = io.BytesIO()
    fmt = "JPEG" if img.mode in ("RGB", "L") else img.format or "PNG"
    img.save(buf, format=fmt, optimize=True)
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

    if source:
        validate_url_ssrf_safe(source)

    if data and data.startswith("data:"):
        mime_part, b64_part = data.split(",", 1)
        fmt = mime_part.split("/")[1].split(";")[0].upper()
        image_bytes = base64.b64decode(b64_part)
    elif source:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
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

    # Storage Backend Integration (FEAT-01)
    from app.core.storage import get_storage_backend
    storage = get_storage_backend()

    ext = fmt.lower()
    filename = f"resized_{uuid.uuid4().hex[:8]}.{ext}"
    content_type = f"image/{ext}" if ext != "jpg" else "image/jpeg"
    storage_key = f"tasks/artifacts/{filename}"

    storage.save(storage_key, resized_bytes, content_type=content_type)

    output_path = payload.get("output_path")
    if output_path:
        target_file = Path(output_path)
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_bytes(resized_bytes)
        output_path_str = str(target_file)
    else:
        output_path_str = storage_key

    logger.info("Image resized and stored via storage backend key: %s (%d bytes)", storage_key, len(resized_bytes))
    return {
        "format": fmt,
        "size_bytes": len(resized_bytes),
        "size_mb": round(result_size_mb, 3),
        "output_path": output_path_str,
        "artifacts": [
            {
                "storage_key": storage_key,
                "filename": filename,
                "content_type": content_type,
                "size_bytes": len(resized_bytes),
            }
        ],
    }
