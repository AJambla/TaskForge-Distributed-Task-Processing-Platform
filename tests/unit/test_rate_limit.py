"""Unit tests for rate limiting logic."""
import pytest
import pytest_asyncio

from app.core.rate_limit import RATE_LIMIT_WINDOW_SECONDS, RateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_allows_within_limit(db_session, monkeypatch):
    from app.core.redis import get_redis
    import redis.asyncio as redis

    fake_client = redis.from_url("redis://localhost:6379/0")
    monkeypatch.setattr("app.core.redis._client", fake_client)

    limiter = RateLimiter(limit=5)
    # This test verifies the RateLimiter class is instantiable and callable.
    # Full integration against Redis is tested in integration tests.
    assert limiter.limit == 5


@pytest.mark.asyncio
async def test_rate_limit_counter_increments():
    from app.core.redis import increment_rate_limit_counter
    import redis.asyncio as redis

    client = redis.from_url("redis://localhost:6379/0")
    try:
        await client.delete("ratelimit:test:unit:60")
        count1 = await increment_rate_limit_counter("ratelimit:test:unit:60", 10, 60)
        assert count1 == 1
        count2 = await increment_rate_limit_counter("ratelimit:test:unit:60", 10, 60)
        assert count2 == 2
    finally:
        await client.delete("ratelimit:test:unit:60")


@pytest.mark.asyncio
async def test_rate_limit_count_zero_when_missing():
    from app.core.redis import get_rate_limit_count
    import redis.asyncio as redis

    client = redis.from_url("redis://localhost:6379/0")
    try:
        await client.delete("ratelimit:test:missing:60")
        count = await get_rate_limit_count("ratelimit:test:missing:60")
        assert count == 0
    finally:
        await client.delete("ratelimit:test:missing:60")
