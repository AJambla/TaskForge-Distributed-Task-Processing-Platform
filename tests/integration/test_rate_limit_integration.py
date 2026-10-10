"""Integration tests for rate limiting against real Redis instance."""
import hashlib
import pytest
from httpx import AsyncClient, ASGITransport

from app.core.rate_limit import make_rate_limiter
from app.core.redis import get_redis
from app.main import app


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_rate_limiter_against_real_redis():
    """Verify rate limiter increments and sets TTL on real Redis."""
    redis_client = await get_redis()
    token = "test-token-unique-real-redis"
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expected_key = f"ratelimit:auth:{token_hash}:60"

    # Ensure clean key
    await redis_client.delete(expected_key)

    limiter = make_rate_limiter(limit=3)

    class FakeRequest:
        method = "POST"
        headers = {"authorization": f"Bearer {token}"}
        client = None

    req = FakeRequest()

    # 3 requests allowed
    await limiter(req)
    await limiter(req)
    await limiter(req)

    count = await redis_client.get(expected_key)
    assert count == "3"

    ttl = await redis_client.ttl(expected_key)
    assert 0 < ttl <= 60

    # 4th request must raise 429 with Retry-After header
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await limiter(req)

    assert exc_info.value.status_code == 429
    assert exc_info.value.headers.get("Retry-After") == "60"

    # Cleanup
    await redis_client.delete(expected_key)


@pytest.mark.asyncio
async def test_separate_users_do_not_collide_on_real_redis():
    """Verify C-05 fix on real Redis: two distinct Bearer tokens have distinct keys."""
    redis_client = await get_redis()
    token_a = "user-a-secret-jwt-token"
    token_b = "user-b-secret-jwt-token"

    key_a = f"ratelimit:auth:{hashlib.sha256(token_a.encode()).hexdigest()}:60"
    key_b = f"ratelimit:auth:{hashlib.sha256(token_b.encode()).hexdigest()}:60"

    await redis_client.delete(key_a)
    await redis_client.delete(key_b)

    limiter = make_rate_limiter(limit=2)

    class ReqA:
        method = "POST"
        headers = {"authorization": f"Bearer {token_a}"}
        client = None

    class ReqB:
        method = "POST"
        headers = {"authorization": f"Bearer {token_b}"}
        client = None

    await limiter(ReqA())
    await limiter(ReqA())

    # User A reaches limit
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        await limiter(ReqA())

    # User B is NOT throttled by User A's requests
    await limiter(ReqB())
    assert await redis_client.get(key_b) == "1"

    # Cleanup
    await redis_client.delete(key_a)
    await redis_client.delete(key_b)
