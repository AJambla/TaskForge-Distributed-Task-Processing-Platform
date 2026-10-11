"""Unit test for synthetic dev database seeder (IMP-11)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
from scripts.seed import seed_database


@pytest.mark.asyncio
async def test_seed_database_creates_users_and_tasks():
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()

    mock_result_none = MagicMock()
    mock_result_none.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result_none

    mock_session_cls = MagicMock()
    mock_session_cls.return_value.__aenter__.return_value = mock_db
    mock_session_cls.return_value.__aexit__.return_value = False

    with patch("scripts.seed.AsyncSessionLocal", mock_session_cls):
        summary = await seed_database(task_count=10)

        assert summary["users"] == 2
        assert summary["tasks"] == 10
        assert mock_db.commit.called
        # Verify tasks were added
        assert mock_db.add.call_count >= 12
