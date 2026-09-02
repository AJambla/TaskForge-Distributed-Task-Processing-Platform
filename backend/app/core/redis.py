"""Async Redis client for idempotency, distributed locks, and rate limiting.

Per DATABASE.md Redis data structures:
- Idempotency key: `idem:{user_id}:{idempotency_key}` with TTL
- Distributed lock: `lock:scheduler:{recurrence_id}` via SET NX PX
- Rate limiting: `ratelimit:{api_key_id}:{window}` fixed-window counter
- Worker heartbeat cache (optional): `worker:heartbeat:{worker_id}`
"""
from __future__ import annotations

import logging

import redis.asyncio as redis

from app.config import get_settings

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None


def _redis_url() -> str:
    settings = get_settings()
    url = settings.redis_url
    # Ensure the URL has a scheme for redis.asyncio
    if not url.startswith(("redis://", "rediss://")):
        url = f"redis://{url}"
    return url


async def get_redis() -> redis.Redis:
    """Lazily create and cache the Redis connection."""
    global _client
    if _client is None:
        settings = get_settings()
        url = settings.redis_url
        _client = redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
    return _client


async def close_redis() -> None:
    """Close the cached Redis connection (called on shutdown)."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None


async def check_idempotency(
    user_id: str, idempotency_key: str, ttl_seconds: int = 86400
) -> bool:
    """Check whether an idempotency key has already been used.

    Returns True if the key already exists (duplicate submission),
    False otherwise. On miss, sets the key with the given TTL.
    """
    client = await get_redis()
    key = f"idem:{user_id}:{idempotency_key}"
    result = await client.set(key, "1", nx=True, ex=ttl_seconds)
    # set returns True on set, False on existing
    return not result  # True = already exists (duplicate)


async def get_idempotency_task_id(
    user_id: str, idempotency_key: str
) -> str | None:
    """Return the task_id stored in the idempotency cache, if any."""
    client = await get_redis()
    key = f"idem:{user_id}:{idempotency_key}"
    value = await client.get(key)
    return value if value else None


async def set_idempotency_task_id(
    user_id: str, idempotency_key: str, task_id: str, ttl_seconds: int = 86400
) -> None:
    """Cache a task_id against an idempotency key for fast duplicate detection."""
    client = await get_redis()
    key = f"idem:{user_id}:{idempotency_key}"
    await client.set(key, task_id, ex=ttl_seconds)


async def acquire_distributed_lock(
    lock_name: str, owner: str, ttl_seconds: int = 10
) -> bool:
    """Acquire a distributed lock using SET NX PX.

    Returns True if the lock was acquired, False if it was already held.
    """
    client = await get_redis()
    key = f"lock:{lock_name}"
    result = await client.set(key, owner, nx=True, ex=ttl_seconds)
    return bool(result)


async def release_distributed_lock(lock_name: str, owner: str) -> None:
    """Release a distributed lock if we own it."""
    client = await get_redis()
    key = f"lock:{lock_name}"
    current = await client.get(key)
    if current == owner:
        await client.delete(key)


async def increment_rate_limit_counter(
    key: str, limit: int, window_seconds: int
) -> int:
    """Increment a fixed-window rate limit counter.

    Returns the new counter value after incrementing.
    Creates the key with the given TTL if it does not exist.
    """
    client = await get_redis()
    count = await client.incr(key)
    if count == 1:
        await client.expire(key, window_seconds)
    return count


async def get_rate_limit_count(key: str) -> int:
    """Return the current count for a rate limit key, or 0 if not set."""
    client = await get_redis()
    value = await client.get(key)
    return int(value) if value else 0
