"""Unit test for image resize handler."""
import base64
import io
from pathlib import Path
import pytest
from PIL import Image

from app.worker.handlers.image import handle_image_resize


@pytest.mark.asyncio
async def test_image_resize_persists_file(tmp_path):
    # Create a 200x200 sample image in base64
    buf = io.BytesIO()
    img = Image.new("RGB", (200, 200), color="blue")
    img.save(buf, format="PNG")
    raw_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    data_uri = f"data:image/png;base64,{raw_b64}"

    out_file = tmp_path / "resized.png"
    payload = {
        "data": data_uri,
        "output_path": str(out_file),
    }

    result = await handle_image_resize(payload)
    assert result["format"] == "JPEG"
    assert result["output_path"] == str(out_file)
    assert out_file.exists()
    assert out_file.stat().st_size > 0
