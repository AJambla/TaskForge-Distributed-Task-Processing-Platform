"""Unit tests for Step 4.1: Sub-Millisecond Redis-Cached Backpressure Admission."""
import pytest
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException

from app.core.rabbitmq import (
    BACKPRESSURE_CACHE_KEY,
    QUEUE_DEPTH_CACHE_KEY,
    check_backpressure,
    sample_queue_depths,
)


@pytest.mark.asyncio
async def test_backpressure_disabled_bypasses_check():
    """When backpressure is disabled, check returns immediately without touching Redis."""
    fake_redis = AsyncMock()
    with patch("app.core.rabbitmq.get_settings") as mock_settings, \
         patch("app.core.redis.get_redis", return_value=fake_redis):
        mock_settings.return_value.backpressure_enabled = False
        await check_backpressure()
        fake_redis.get.assert_not_called()


@pytest.mark.asyncio
async def test_sub_millisecond_cache_hit_under_threshold():
    """When cached queue depth is below critical depth, no exception is raised and no HTTP calls made."""
    fake_redis = AsyncMock()
    fake_redis.get.side_effect = lambda k: "250" if k == BACKPRESSURE_CACHE_KEY else None

    with patch("app.core.rabbitmq.get_settings") as mock_settings, \
         patch("app.core.redis.get_redis", return_value=fake_redis), \
         patch("app.core.rabbitmq.get_queue_depths") as mock_get_depths:

        mock_settings.return_value.backpressure_enabled = True
        mock_settings.return_value.backpressure_critical_depth = 500
        mock_settings.return_value.backpressure_queue_depth_threshold = 500

        await check_backpressure()

        mock_get_depths.assert_not_called()


@pytest.mark.asyncio
async def test_backpressure_raises_429_with_retry_after_5():
    """When depth exceeds backpressure_critical_depth, raise 429 with Retry-After: 5."""
    fake_redis = AsyncMock()
    fake_redis.get.return_value = "750"

    with patch("app.core.rabbitmq.get_settings") as mock_settings, \
         patch("app.core.redis.get_redis", return_value=fake_redis):

        mock_settings.return_value.backpressure_enabled = True
        mock_settings.return_value.backpressure_critical_depth = 500
        mock_settings.return_value.backpressure_queue_depth_threshold = 500

        with pytest.raises(HTTPException) as exc_info:
            await check_backpressure()

        exc = exc_info.value
        assert exc.status_code == 429
        assert exc.headers.get("Retry-After") == "5"
        assert exc.detail["error"]["code"] == "QUEUE_FULL"
        assert "Task queue saturated, system in backpressure shedding mode" in exc.detail["error"]["message"]


@pytest.mark.asyncio
async def test_backpressure_cache_miss_triggers_fast_sample():
    """On cache miss, sample_queue_depths fetches depths and caches with 2s TTL."""
    fake_redis = AsyncMock()
    fake_redis.get.return_value = None

    with patch("app.core.rabbitmq.get_settings") as mock_settings, \
         patch("app.core.redis.get_redis", return_value=fake_redis), \
         patch("app.core.rabbitmq.get_queue_depths", new_callable=AsyncMock) as mock_get_depths:

        mock_settings.return_value.backpressure_enabled = True
        mock_settings.return_value.backpressure_critical_depth = 500
        mock_settings.return_value.backpressure_queue_depth_threshold = 500
        mock_get_depths.return_value = {
            "tasks.high": 120,
            "tasks.normal": 80,
            "tasks.low": 20,
        }

        await check_backpressure()

        mock_get_depths.assert_awaited_once()
        fake_redis.set.assert_awaited_once_with(BACKPRESSURE_CACHE_KEY, 220, ex=2)


@pytest.mark.asyncio
async def test_sample_queue_depths_custom_key():
    """sample_queue_depths supports custom cache key like queue:total_depth."""
    fake_redis = AsyncMock()
    with patch("app.core.rabbitmq.get_queue_depths", new_callable=AsyncMock) as mock_get_depths:
        mock_get_depths.return_value = {"tasks.default": 42}
        total = await sample_queue_depths(redis_client=fake_redis, key=QUEUE_DEPTH_CACHE_KEY)
        assert total == 42
        fake_redis.set.assert_awaited_once_with(QUEUE_DEPTH_CACHE_KEY, 42, ex=2)


@pytest.mark.asyncio
async def test_backpressure_fails_open_on_redis_and_management_failure():
    """If Redis and management API both fail, check_backpressure fails open gracefully."""
    with patch("app.core.rabbitmq.get_settings") as mock_settings, \
         patch("app.core.redis.get_redis", side_effect=RuntimeError("Redis down")), \
         patch("app.core.rabbitmq.get_queue_depths", new_callable=AsyncMock, return_value={}):

        mock_settings.return_value.backpressure_enabled = True
        mock_settings.return_value.backpressure_critical_depth = 100
        mock_settings.return_value.backpressure_queue_depth_threshold = 100

        # Should not raise any exception
        await check_backpressure()
