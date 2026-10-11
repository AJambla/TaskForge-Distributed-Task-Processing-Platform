"""Unit test for image resize external plugin (FEAT-06)."""
import base64
import io
import pytest
from unittest.mock import AsyncMock, MagicMock
from PIL import Image

from image_plugin.handler import handle_image_resize, ImageResizePayload
from app.worker.context import TaskContext
from app.worker.handlers import get_handler, list_handlers


@pytest.mark.asyncio
async def test_image_resize_plugin_handler():
    # Verify handler is registered in the TaskForge SPI
    handlers = list_handlers()
    assert "image_resize" in handlers
    assert callable(get_handler("image_resize"))

    # Create a 200x200 sample image in base64
    buf = io.BytesIO()
    img = Image.new("RGB", (200, 200), color="blue")
    img.save(buf, format="PNG")
    raw_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    data_uri = f"data:image/png;base64,{raw_b64}"

    payload = {
        "data": data_uri,
        "width": 100,
        "height": 100,
    }

    # Validate schema
    parsed_payload = ImageResizePayload(**payload)
    assert parsed_payload.width == 100

    # Instantiate TaskContext
    ctx = TaskContext(
        task_id="task-test-image-plugin",
        task_type="image_resize",
        attempt=1,
    )
    ctx.set_progress = AsyncMock()

    result = await handle_image_resize(payload, ctx)
    assert result["format"] == "JPEG"
    assert "artifacts" in result
    assert len(result["artifacts"]) == 1
    assert result["artifacts"][0]["content_type"] == "image/jpeg"
    assert ctx.set_progress.called
