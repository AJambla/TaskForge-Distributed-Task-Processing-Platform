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
async def _clear_redis_counters() -> None:
    """Auth/submission rate-limit and idempotency counters persist in Redis
    for a 60s window; wipe them so each test starts unthrottled."""
    from app.core.redis import get_redis

    client = await get_redis()
    for pattern in ("ratelimit:*", "idem:*"):
        async for key in client.scan_iter(match=pattern):
            await client.delete(key)


@pytest_asyncio.fixture(autouse=True)
async def _reset_app_singletons() -> AsyncGenerator[None, None]:
    """pytest-asyncio gives each test a fresh event loop, but the app module
    keeps pooled clients (DB engine, Redis, RabbitMQ) alive between tests.
    Close them after every test so no connection is reused across loops."""
    yield
    from app.core.rabbitmq import close_publisher
    from app.core.redis import close_redis
    from app.database import engine as app_engine

    await close_redis()
    await close_publisher()
    await app_engine.dispose()


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
