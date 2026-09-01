"""Integration tests for refresh token rotation."""
from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.main import app
from app.models.refresh_token import RefreshToken


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_refresh_returns_new_token(client, db_session):
    """Login gives a refresh token; refreshing returns a new one."""
    # Register and login
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "rotator@example.com", "password": "RotatorPass1!"},
    )
    assert resp.status_code == 201

    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "rotator@example.com", "password": "RotatorPass1!"},
    )
    assert login_resp.status_code == 200
    login_data = login_resp.json()
    old_refresh = login_data["refresh_token"]
    assert "access_token" in login_data
    assert "refresh_token" in login_data
    assert "expires_in" in login_data

    # Refresh using the old token
    refresh_resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh},
    )
    assert refresh_resp.status_code == 200
    refresh_data = refresh_resp.json()
    assert "access_token" in refresh_data
    assert "refresh_token" in refresh_data
    assert "expires_in" in refresh_data
    assert refresh_data["refresh_token"] != old_refresh

    # Verify old token is revoked
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(RefreshToken).where(RefreshToken.user_id == login_data.get("user_id"))
        )
        # Find the old token by checking hashes — we can't easily match without
        # the raw token, but we know the new one should NOT be revoked
        all_tokens = result.scalars().all()
        assert len(all_tokens) >= 2
        # At least one should be revoked (the old one)
        revoked_count = sum(1 for t in all_tokens if t.revoked)
        assert revoked_count >= 1


@pytest.mark.asyncio
async def test_revoked_refresh_token_rejected(client, db_session):
    """Using a revoked refresh token returns 401."""
    # Register and login
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "revoker@example.com", "password": "RevokerPass1!"},
    )
    assert resp.status_code == 201

    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "revoker@example.com", "password": "RevokerPass1!"},
    )
    old_refresh = login_resp.json()["refresh_token"]

    # Revoke via logout
    access_token = login_resp.json()["access_token"]
    await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    # Try to use the revoked token
    refresh_resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh},
    )
    assert refresh_resp.status_code == 401
    assert refresh_resp.json()["error"]["code"] == "INVALID_REFRESH_TOKEN"


@pytest.mark.asyncio
async def test_refresh_response_schema(client):
    """Verify the refresh response includes refresh_token field."""
    # Register and login
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "schema@example.com", "password": "SchemaPass1!"},
    )
    assert resp.status_code == 201

    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "schema@example.com", "password": "SchemaPass1!"},
    )
    old_refresh = login_resp.json()["refresh_token"]

    refresh_resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh},
    )
    assert refresh_resp.status_code == 200
    data = refresh_resp.json()
    assert "refresh_token" in data
    assert isinstance(data["refresh_token"], str)
    assert len(data["refresh_token"]) > 0
