"""Integration tests for backpressure."""
from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch

from app.main import app
from app.config import get_settings


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def _login(client, email: str, password: str) -> str:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_backpressure_disabled_allows_submission(client, regular_user):
    """When backpressure is disabled, submission proceeds normally."""
    token = await _login(client, "user@example.com", "UserPass1!")

    with patch("app.routers.tasks.check_backpressure") as mock_check:
        mock_check.return_value = None
        resp = await client.post(
            "/api/v1/tasks",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "task_type": "email_send",
                "payload": {
                    "to": "test@example.com",
                    "subject": "Test",
                    "body": "Hello",
                },
            },
        )
        # mock_check is called but RabbitMQ publish may fail (no broker)
        # We just verify the backpressure check was invoked
        mock_check.assert_called_once()
        # Status will be 503 due to no RabbitMQ, but not 429
        assert resp.status_code != 429


@pytest.mark.asyncio
async def test_backpressure_enabled_returns_429(client, regular_user):
    """When backpressure threshold is exceeded, return 429."""
    token = await _login(client, "user@example.com", "UserPass1!")

    with patch("app.routers.tasks.check_backpressure") as mock_check:
        from fastapi import HTTPException
        mock_check.side_effect = HTTPException(
            status_code=429,
            detail={
                "error": {
                    "code": "QUEUE_FULL",
                    "message": "System is backpressuring. Please retry.",
                    "field": None,
                }
            },
            headers={"Retry-After": "30"},
        )
        resp = await client.post(
            "/api/v1/tasks",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "task_type": "email_send",
                "payload": {
                    "to": "test@example.com",
                    "subject": "Test",
                    "body": "Hello",
                },
            },
        )
        assert resp.status_code == 429
        assert resp.json()["error"]["code"] == "QUEUE_FULL"
        assert resp.headers.get("Retry-After") == "30"


@pytest.mark.asyncio
async def test_backpressure_config_defaults():
    """Verify backpressure config defaults."""
    settings = get_settings()
    assert settings.backpressure_enabled is False
    assert settings.backpressure_queue_depth_threshold == 500
