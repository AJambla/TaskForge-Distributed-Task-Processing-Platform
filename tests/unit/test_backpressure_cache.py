"""Unit tests for backpressure queue depth caching (IMP-01)."""
import pytest
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException

from app.core.rabbitmq import check_backpressure


@pytest.mark.asyncio
async def test_check_backpressure_uses_redis_cache():
    """Verify check_backpressure reads from Redis cache and avoids management API call on hit."""
    fake_redis = AsyncMock()
    fake_redis.get.return_value = "100"  # Below threshold

    with patch("app.core.rabbitmq.get_settings") as mock_settings, \
         patch("app.core.redis.get_redis", return_value=fake_redis), \
         patch("app.core.rabbitmq.get_queue_depths") as mock_depths:

        mock_settings.return_value.backpressure_enabled = True
        mock_settings.return_value.backpressure_queue_depth_threshold = 500

        await check_backpressure()

        fake_redis.get.assert_awaited_once_with("backpressure:total_depth")
        mock_depths.assert_not_called()


@pytest.mark.asyncio
async def test_check_backpressure_caches_on_miss():
    """Verify check_backpressure queries management API on miss and writes to Redis with 2s TTL."""
    fake_redis = AsyncMock()
    fake_redis.get.return_value = None  # Cache miss

    with patch("app.core.rabbitmq.get_settings") as mock_settings, \
         patch("app.core.redis.get_redis", return_value=fake_redis), \
         patch("app.core.rabbitmq.get_queue_depths", new_callable=AsyncMock) as mock_depths:

        mock_settings.return_value.backpressure_enabled = True
        mock_settings.return_value.backpressure_queue_depth_threshold = 500
        mock_depths.return_value = {"tasks.email": 50, "tasks.image": 100}

        await check_backpressure()

        mock_depths.assert_awaited_once()
        fake_redis.set.assert_awaited_once_with("backpressure:total_depth", 150, ex=2)


@pytest.mark.asyncio
async def test_check_backpressure_raises_429_on_threshold_exceeded():
    """Verify check_backpressure raises 429 when cached depth exceeds threshold."""
    fake_redis = AsyncMock()
    fake_redis.get.return_value = "600"  # Above 500 threshold

    with patch("app.core.rabbitmq.get_settings") as mock_settings, \
         patch("app.core.redis.get_redis", return_value=fake_redis):

        mock_settings.return_value.backpressure_enabled = True
        mock_settings.return_value.backpressure_queue_depth_threshold = 500

        with pytest.raises(HTTPException) as exc_info:
            await check_backpressure()

        assert exc_info.value.status_code == 429
        assert exc_info.value.detail["error"]["code"] == "QUEUE_FULL"
