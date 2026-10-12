"""Regression test for CRIT-05: Enforce download size limit in image_resize handler."""
from __future__ import annotations

import base64
from unittest.mock import AsyncMock, patch
import pytest

from image_plugin.handler import MAX_IMAGE_DOWNLOAD_BYTES, handle_image_resize


@pytest.mark.asyncio
async def test_image_data_uri_rejects_oversized_payload():
    """Verify base64 payload larger than 15MB is rejected with ValueError."""
    ctx = AsyncMock()
    # Create dummy base64 payload representing 16MB of data
    oversized_raw = b"A" * (MAX_IMAGE_DOWNLOAD_BYTES + 1024)
    b64_str = base64.b64encode(oversized_raw).decode("ascii")
    payload = {"data": f"data:image/png;base64,{b64_str}"}

    with pytest.raises(ValueError, match="Image payload exceeds maximum allowed size"):
        await handle_image_resize(payload, ctx)


@pytest.mark.asyncio
async def test_image_download_rejects_oversized_stream():
    """Verify streaming download aborts when chunks exceed MAX_IMAGE_DOWNLOAD_BYTES."""
    ctx = AsyncMock()
    payload = {"source_url": "https://example.com/huge-image.jpg"}

    # Mock chunk generator that produces chunks exceeding the limit
    async def mock_aiter_bytes():
        chunk = b"X" * (5 * 1024 * 1024)  # 5MB chunk
        for _ in range(4):  # 4 * 5MB = 20MB > 15MB
            yield chunk

    mock_resp = AsyncMock()
    mock_resp.headers = {"content-length": str(20 * 1024 * 1024)}
    mock_resp.raise_for_status = AsyncMock()
    mock_resp.aiter_bytes = mock_aiter_bytes

    class MockStreamContext:
        async def __aenter__(self):
            return mock_resp
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return False

    with patch("image_plugin.handler.validate_url_ssrf_safe"):
        with patch("httpx.AsyncClient.stream", return_value=MockStreamContext()):
            with pytest.raises(ValueError, match="Image download exceeds maximum allowed size"):
                await handle_image_resize(payload, ctx)
