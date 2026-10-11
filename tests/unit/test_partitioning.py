"""Unit tests for PostgreSQL range partitioning utility (IMP-14)."""
import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone
from app.core.partitioning import (
    generate_partition_month_bounds,
    generate_create_partition_sql,
    provision_partitions_for_window,
)


def test_generate_partition_month_bounds():
    suffix, start, end = generate_partition_month_bounds(2026, 10)
    assert suffix == "y2026m10"
    assert start == "2026-10-01 00:00:00+00"
    assert end == "2026-11-01 00:00:00+00"

    # Year rollover test
    suffix_dec, start_dec, end_dec = generate_partition_month_bounds(2026, 12)
    assert suffix_dec == "y2026m12"
    assert start_dec == "2026-12-01 00:00:00+00"
    assert end_dec == "2027-01-01 00:00:00+00"


def test_generate_create_partition_sql():
    sql = generate_create_partition_sql("tasks", 2026, 10)
    assert "CREATE TABLE IF NOT EXISTS tasks_y2026m10" in sql
    assert "PARTITION OF tasks" in sql
    assert "FOR VALUES FROM ('2026-10-01 00:00:00+00') TO ('2026-11-01 00:00:00+00')" in sql


@pytest.mark.asyncio
async def test_provision_partitions_for_window():
    mock_db = AsyncMock()
    base_date = datetime(2026, 10, 15, tzinfo=timezone.utc)

    ensured = await provision_partitions_for_window(
        mock_db,
        table_name="tasks",
        months_ahead=2,
        base_date=base_date,
    )

    # 10, 11, 12 = 3 months
    assert len(ensured) == 3
    assert "tasks_y2026m10" in ensured
    assert "tasks_y2026m11" in ensured
    assert "tasks_y2026m12" in ensured
    assert mock_db.execute.call_count == 3
    assert mock_db.commit.called
