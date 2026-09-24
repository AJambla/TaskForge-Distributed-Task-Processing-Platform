"""Test configuration — shared fixtures for unit and integration tests.

Note: the autouse database setup/teardown that needs a live Postgres lives
in tests/integration/conftest.py, so unit tests run without any services.
"""
from __future__ import annotations

import os
import sys
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

# Ensure backend/app is importable from tests/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Make the app's own settings (and thus AsyncSessionLocal) target the test
# database, so the session fixtures and the schema setup/teardown in
# tests/integration/conftest.py operate on the same DB. Must run before any
# app import below, since Settings is cached at import time.
_DEFAULT_URL = (
    "postgresql+asyncpg://taskforge:taskforge_dev_secret@localhost:5432/taskforge"
)
_test_url = os.environ.get("TEST_DATABASE_URL") or (
    os.environ.get("DATABASE_URL", _DEFAULT_URL).rsplit("/", 1)[0]
    + "/taskforge_test"
)
os.environ["TEST_DATABASE_URL"] = _test_url
os.environ["DATABASE_URL"] = _test_url

from app.core.security import hash_password
from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.worker_registration import WorkerRegistration


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional database session for each test."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    """Create and return an admin user."""
    user = User(
        email="admin@example.com",
        password_hash=hash_password("AdminPass1!"),
        role="admin",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def regular_user(db_session: AsyncSession) -> User:
    """Create and return a regular user."""
    user = User(
        email="user@example.com",
        password_hash=hash_password("UserPass1!"),
        role="user",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_jwt(client) -> str:
    """Return a JWT access token for the admin user."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "AdminPass1!"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest_asyncio.fixture
async def regular_jwt(client) -> str:
    """Return a JWT access token for the regular user."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "UserPass1!"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest_asyncio.fixture
async def worker(db_session: AsyncSession, admin_user: User) -> WorkerRegistration:
    """Create and return a worker registration."""
    worker = WorkerRegistration(
        hostname="test-worker-1",
        status="online",
        concurrency_limit=4,
    )
    db_session.add(worker)
    await db_session.commit()
    await db_session.refresh(worker)
    return worker
