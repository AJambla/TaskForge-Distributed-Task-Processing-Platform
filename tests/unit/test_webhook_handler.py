"""Unit test for webhook delivery handler."""
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.worker.handlers.webhook import handle_webhook_delivery


@pytest.mark.asyncio
async def test_webhook_error_sanitized():
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.reason_phrase = "Internal Server Error"
    mock_resp.text = "<html><body><h1>SQLSTATE[HY000]: Database error details leak</h1></body></html>"
    mock_resp.content = b"<html>error</html>"

    with patch("httpx.AsyncClient") as mock_client_cls:
        client_instance = AsyncMock()
        client_instance.post.return_value = mock_resp
        client_instance.__aenter__.return_value = client_instance
        client_instance.__aexit__.return_value = None
        mock_client_cls.return_value = client_instance

        with patch("app.worker.handlers.webhook.validate_url_ssrf_safe"):
            with pytest.raises(ValueError) as excinfo:
                await handle_webhook_delivery({"url": "https://example.com/hook", "body": {}})

            err_msg = str(excinfo.value)
            assert "HTTP 500 (Internal Server Error)" in err_msg
            assert "SQLSTATE" not in err_msg
            assert "<html>" not in err_msg
