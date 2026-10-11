"""PostgreSQL declarative range partitioning utilities for TaskForge (IMP-14).

Generates and provisions monthly partitions for hot tables (`tasks`, `task_attempts`)
to maintain constant-time index updates, instant point-in-time pruning,
and efficient VACUUM operations at massive scale.
"""
from __future__ import annotations

import calendar
import logging
from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def generate_partition_month_bounds(year: int, month: int) -> tuple[str, str, str]:
    """Calculate partition suffix, start timestamp, and end timestamp for a month.

    Returns:
        (suffix, start_iso, end_iso) where suffix is 'yYYYYmMM'
    """
    _, last_day = calendar.monthrange(year, month)
    suffix = f"y{year:04d}m{month:02d}"
    start_bound = f"{year:04d}-{month:02d}-01 00:00:00+00"

    # End bound is the first day of next month
    if month == 12:
        end_bound = f"{year + 1:04d}-01-01 00:00:00+00"
    else:
        end_bound = f"{year:04d}-{month + 1:02d}-01 00:00:00+00"

    return suffix, start_bound, end_bound


def generate_create_partition_sql(table_name: str, year: int, month: int) -> str:
    """Generate DDL statement to create a monthly range partition table."""
    suffix, start_bound, end_bound = generate_partition_month_bounds(year, month)
    partition_table_name = f"{table_name}_{suffix}"
    return (
        f"CREATE TABLE IF NOT EXISTS {partition_table_name} "
        f"PARTITION OF {table_name} "
        f"FOR VALUES FROM ('{start_bound}') TO ('{end_bound}');"
    )


async def provision_partitions_for_window(
    db: AsyncSession,
    table_name: str,
    months_ahead: int = 3,
    base_date: datetime | None = None,
) -> list[str]:
    """Ensure monthly partitions exist for current month and N months into the future.

    Returns list of partition table names ensured.
    """
    if base_date is None:
        base_date = datetime.now(timezone.utc)

    year = base_date.year
    month = base_date.month

    ensured_tables = []
    for _ in range(months_ahead + 1):
        suffix, _, _ = generate_partition_month_bounds(year, month)
        part_name = f"{table_name}_{suffix}"
        sql = generate_create_partition_sql(table_name, year, month)
        try:
            await db.execute(text(sql))
            ensured_tables.append(part_name)
        except Exception as exc:
            logger.warning("Could not execute partition DDL for %s: %s", part_name, exc)
            # Fails gracefully if parent table is not yet partitioned in test env

        month += 1
        if month > 12:
            month = 1
            year += 1

    await db.commit()
    return ensured_tables
