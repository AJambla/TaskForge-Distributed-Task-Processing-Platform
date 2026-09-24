"""Unit tests for rate limiting logic — no live Redis or Postgres required."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.core import redis as redis_module
from app.core.rate_limit import RATE_LIMIT_WINDOW_SECONDS, make_rate_limiter


class FakeRedis:
    """Minimal async Redis stand-in covering the commands used by rate limiting."""

    def __init__(self):
        self.store: dict[str, str] = {}
        self.expirations: list[tuple[str, int]] = []

    async def incr(self, key: str) -> int:
        self.store[key] = str(int(self.store.get(key, "0")) + 1)
        return int(self.store[key])

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def expire(self, key: str, seconds: int) -> bool:
        self.expirations.append((key, seconds))
        return True


@pytest.fixture
def fake_redis(monkeypatch) -> FakeRedis:
    client = FakeRedis()
    monkeypatch.setattr(redis_module, "_client", client)
    return client


class FakeRequest:
    def __init__(self, headers: dict | None = None):
        self.method = "POST"
        self.headers = headers or {}
        self.client = None


async def test_window_constant():
    assert RATE_LIMIT_WINDOW_SECONDS == 60


async def test_allows_requests_within_limit(fake_redis):
    limiter = make_rate_limiter(limit=3)
    token = "tok-abcdefghijk1234"
    request = FakeRequest({"authorization": f"Bearer {token}"})

    for _ in range(3):
        await limiter(request)

    assert await fake_redis.get(f"ratelimit:auth:{token[:16]}:60") == "3"


async def test_raises_429_over_limit(fake_redis):
    limiter = make_rate_limiter(limit=2)
    request = FakeRequest()

    await limiter(request)
    await limiter(request)
    with pytest.raises(HTTPException) as exc_info:
        await limiter(request)

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["error"]["code"] == "RATE_LIMITED"


async def test_api_key_and_bearer_use_separate_counters(fake_redis):
    limiter = make_rate_limiter(limit=5)
    token = "tok-abcdefghijk1234"
    bearer_request = FakeRequest({"authorization": f"Bearer {token}"})
    api_key_request = FakeRequest()

    await limiter(bearer_request)
    await limiter(api_key_request, api_key_header="tf_live_key123")

    assert await fake_redis.get(f"ratelimit:auth:{token[:16]}:60") == "1"
    assert await fake_redis.get("ratelimit:tf_live_key123:60") == "1"


async def test_options_requests_skip_rate_limiting(fake_redis):
    limiter = make_rate_limiter(limit=1)
    request = FakeRequest()
    request.method = "OPTIONS"

    for _ in range(5):
        await limiter(request)

    assert fake_redis.store == {}


async def test_counter_sets_ttl_only_on_first_increment(fake_redis):
    from app.core.redis import increment_rate_limit_counter

    key = "ratelimit:unit:60"
    assert await increment_rate_limit_counter(key, 10, 60) == 1
    assert await increment_rate_limit_counter(key, 10, 60) == 2
    assert fake_redis.expirations == [(key, 60)]


async def test_get_rate_limit_count_zero_when_missing(fake_redis):
    from app.core.redis import get_rate_limit_count

    assert await get_rate_limit_count("ratelimit:missing:60") == 0
