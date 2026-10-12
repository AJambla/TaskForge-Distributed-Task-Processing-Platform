"""Regression test for CRIT-01: SSRF protection in image_resize handler."""
from __future__ import annotations

from unittest.mock import AsyncMock
import pytest

from image_plugin.handler import handle_image_resize


@pytest.mark.asyncio
async def test_image_resize_blocks_loopback_ssrf():
    """Verify handle_image_resize rejects requests targeting loopback addresses."""
    ctx = AsyncMock()
    payload = {"source_url": "http://127.0.0.1:8080/internal.png"}
    with pytest.raises(ValueError, match="SSRF protection.*internal IP address"):
        await handle_image_resize(payload, ctx)


@pytest.mark.asyncio
async def test_image_resize_blocks_cloud_metadata_ssrf():
    """Verify handle_image_resize rejects cloud metadata service requests."""
    ctx = AsyncMock()
    payload = {"source_url": "http://169.254.169.254/latest/meta-data/"}
    with pytest.raises(ValueError, match="SSRF protection.*internal IP address"):
        await handle_image_resize(payload, ctx)
