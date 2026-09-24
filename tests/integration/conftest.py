"""Integration test configuration — requires live Postgres.

The autouse fixture creates all ORM tables before each test and drops them
afterwards, mirroring the original root-conftest behavior.
"""
from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Import all models so Base.metadata knows every table.
import app.models.api_key  # noqa: F401
import app.models.refresh_token  # noqa: F401
import app.models.task  # noqa: F401
import app.models.task_attempt  # noqa: F401
import app.models.user  # noqa: F401
import app.models.worker_registration  # noqa: F401
from app.models.base import Base

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
