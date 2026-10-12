"""Regression test for CRIT-03: Require admin role on DLQ redrive."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.deps import get_current_user, get_db
from app.main import app
from app.models.user import User


@pytest.mark.asyncio
async def test_dlq_redrive_forbidden_for_regular_user():
    """Verify that a standard user receives 403 Forbidden on POST /api/v1/queues/dlq/redrive."""
    regular_user = User(
        id=uuid.uuid4(),
        email="dev@example.com",
        role="user",
    )
    mock_db = AsyncMock()

    app.dependency_overrides[get_current_user] = lambda: regular_user
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v1/queues/dlq/redrive")
            assert resp.status_code == 403
            data = resp.json()
            assert data["error"]["code"] == "FORBIDDEN"
            assert "Admin role required" in data["error"]["message"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_dlq_redrive_allowed_for_admin_user():
    """Verify that an admin user passes the RBAC check on POST /api/v1/queues/dlq/redrive."""
    admin_user = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        role="admin",
    )
    mock_db = AsyncMock()
    # Mock empty scalar result for Task select query
    from unittest.mock import MagicMock
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result

    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v1/queues/dlq/redrive")
            assert resp.status_code == 200
            assert resp.json()["redriven_count"] == 0
    finally:
        app.dependency_overrides.clear()
