"""Test configuration — shared fixtures for unit and integration tests."""
from __future__ import annotations

import os
import sys
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# Ensure backend/app is importable from tests/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings
from app.core.security import hash_password
from app.database import Base, AsyncSessionLocal
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.models.worker_registration import WorkerRegistration
from app.models.task import Task
from app.models.task_attempt import TaskAttempt

# Use test database URL if available, otherwise default to localhost
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://taskforge:taskforge_dev_secret@localhost:5432/taskforge_test",
)
engine = create_async_engine(TEST_DATABASE_URL, echo=False)


@pytest_asyncio.fixture(autouse=True)
async def setup_and_teardown_db() -> AsyncGenerator[None, None]:
    """Create tables before tests and drop them after."""
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS public"))
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(text(f"DELETE FROM {table.name}"))
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


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
    await db_session.flush()
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
    await db_session.flush()
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
    await db_session.flush()
    await db_session.refresh(worker)
    return worker
