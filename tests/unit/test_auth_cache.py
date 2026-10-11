"""Unit tests for user and API key Redis authentication caching (IMP-04)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
import json

from app.core.deps import _auth_via_jwt, _auth_via_api_key
from app.core.security import create_access_token, hash_api_key
from app.models.user import User
from app.models.api_key import APIKey


@pytest.mark.asyncio
async def test_auth_via_jwt_uses_redis_cache():
    """Verify _auth_via_jwt uses cached user data from Redis when present."""
    user_id = uuid.uuid4()
    token, _ = create_access_token(user_id, role="user")

    cached_data = {
        "id": str(user_id),
        "email": "cached@example.com",
        "role": "user",
        "password_hash": "hash123",
    }

    fake_redis = AsyncMock()
    fake_redis.get.return_value = json.dumps(cached_data)

    mock_db = AsyncMock()

    with patch("app.core.redis.get_redis", return_value=fake_redis):
        user = await _auth_via_jwt(token, mock_db)

        assert user.id == user_id
        assert user.email == "cached@example.com"
        assert user.role == "user"
        fake_redis.get.assert_awaited_once_with(f"auth:user:{user_id}")
        # DB should not be queried when cache hits
        mock_db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_auth_via_jwt_caches_on_db_miss():
    """Verify _auth_via_jwt queries DB on cache miss and writes to Redis with 60s TTL."""
    user_id = uuid.uuid4()
    token, _ = create_access_token(user_id, role="user")

    fake_redis = AsyncMock()
    fake_redis.get.return_value = None  # Cache miss

    db_user = User(
        id=user_id,
        email="db@example.com",
        password_hash="hash456",
        role="admin",
    )

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = db_user
    mock_db.execute.return_value = mock_result

    with patch("app.core.redis.get_redis", return_value=fake_redis):
        user = await _auth_via_jwt(token, mock_db)

        assert user.id == user_id
        assert user.email == "db@example.com"
        assert user.role == "admin"
        mock_db.execute.assert_awaited_once()
        fake_redis.set.assert_awaited_once()
        args, kwargs = fake_redis.set.call_args
        assert args[0] == f"auth:user:{user_id}"
        assert kwargs["ex"] == 60
