"""Integration tests for auth endpoints."""
from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.main import app


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


async def _register(client, email: str, password: str) -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_register_and_login(client):
    await _register(client, "newuser@example.com", "NewPass1!")

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "newuser@example.com", "password": "NewPass1!"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert "expires_in" in data


@pytest.mark.asyncio
async def test_login_invalid_credentials(client):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "WrongPass1!"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_duplicate_registration(client):
    await _register(client, "dup@example.com", "DupPass1!")
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "dup@example.com", "password": "DupPass1!"},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED"


@pytest.mark.asyncio
async def test_logout_revokes_all_tokens(client, db_session, admin_user):
    access_token = await _login(client, "admin@example.com", "AdminPass1!")

    # Get the refresh token
    result = await db_session.execute(
        select(RefreshToken).where(RefreshToken.user_id == admin_user.id)
    )
    refresh_record = result.scalar_one_or_none()
    assert refresh_record is not None

    # Logout
    resp = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert resp.status_code == 204

    # Verify token is revoked
    await db_session.refresh(refresh_record)
    assert refresh_record.revoked is True
