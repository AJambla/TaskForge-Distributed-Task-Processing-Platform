"""Unit test for API key authentication debounced last_used_at update."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.core.deps import _auth_via_api_key


@pytest.mark.asyncio
async def test_api_key_last_used_at_debounced():
    db = MagicMock()
    db.commit = AsyncMock()
    db.execute = AsyncMock()

    mock_key = MagicMock()
    mock_key.id = uuid.uuid4()
    mock_key.is_active = True
    mock_key.user_id = uuid.uuid4()

    mock_user = MagicMock()
    mock_user.id = mock_key.user_id

    # db.execute returns mock_key on first call, mock_user on second
    result_key = MagicMock()
    result_key.scalar_one_or_none.return_value = mock_key
    result_user = MagicMock()
    result_user.scalar_one_or_none.return_value = mock_user

    db.execute.side_effect = [result_key, result_user]

    fake_redis = AsyncMock()
    # redis.set returns False (key was already set within 60s)
    fake_redis.set.return_value = False

    with patch("app.core.redis.get_redis", AsyncMock(return_value=fake_redis)):
        with patch("app.core.deps.hash_api_key", return_value="dummy_hash"):
            user = await _auth_via_api_key("tf_live_samplekey", db)
            assert user == mock_user
            # Should NOT commit because should_update is False
            db.commit.assert_not_awaited()
