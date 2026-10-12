"""Priority anti-starvation fairness and weighted queue consumption (Step 4.3)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Final

logger = logging.getLogger("worker.priority")

PRIORITY_TIERS: Final[list[str]] = ["high", "normal", "low"]
DEFAULT_PRIORITY_WEIGHTS: Final[dict[str, int]] = {
    "high": 6,    # 60% of capacity
    "normal": 3,  # 30% of capacity
    "low": 1,     # 10% of capacity
}


def get_priority_tier(priority: int) -> str:
    """Classify an integer priority (0-10) into a tier: 'high', 'normal', 'low'."""
    try:
        p = int(priority)
    except (ValueError, TypeError):
        p = 0
    if p >= 7:
        return "high"
    elif p >= 3:
        return "normal"
    else:
        return "low"


def get_priority_queue_name(priority: int) -> str:
    """Return priority queue name: 'tasks.high', 'tasks.normal', 'tasks.low'."""
    return f"tasks.{get_priority_tier(priority)}"


class PriorityFairDispatcher:
    """Weighted Fair Queueing (WFQ) dispatcher across priority tiers.

    Enforces 60% high, 30% normal, 10% low weighted consumption.
    Guarantees low-priority tasks make steady progress and are not permanently
    starved under sustained surges of high-priority tasks.
    """

    def __init__(
        self,
        weights: dict[str, int] | None = None,
        concurrency: int = 4,
    ) -> None:
        self.weights = dict(weights or DEFAULT_PRIORITY_WEIGHTS)
        self.concurrency = concurrency
        self._semaphore = asyncio.BoundedSemaphore(concurrency)
        self._queues: dict[str, asyncio.Queue] = {
            tier: asyncio.Queue() for tier in PRIORITY_TIERS
        }
        self._remaining: dict[str, int] = dict(self.weights)
        self._notify_event = asyncio.Event()
        self._processed_counts: dict[str, int] = {tier: 0 for tier in PRIORITY_TIERS}

    @property
    def semaphore(self) -> asyncio.BoundedSemaphore:
        return self._semaphore

    @property
    def stats(self) -> dict[str, Any]:
        """Return current queue depths and processed counts by tier."""
        return {
            "depths": {tier: q.qsize() for tier, q in self._queues.items()},
            "processed": dict(self._processed_counts),
            "remaining_quota": dict(self._remaining),
        }

    def enqueue(self, item: Any, tier: str | None = None, priority: int | None = None) -> None:
        """Enqueue an item into its priority tier buffer.

        If tier is omitted, derives tier from priority or item attributes.
        """
        if tier is None:
            if priority is not None:
                tier = get_priority_tier(priority)
            elif hasattr(item, "priority"):
                tier = get_priority_tier(item.priority)
            elif isinstance(item, dict) and "priority" in item:
                tier = get_priority_tier(item["priority"])
            else:
                tier = "normal"

        if tier not in self._queues:
            tier = "normal"

        self._queues[tier].put_nowait(item)
        self._notify_event.set()

    def _reset_weights_if_exhausted(self) -> None:
        if all(count <= 0 for count in self._remaining.values()):
            self._remaining = dict(self.weights)

    def select_next(self) -> tuple[str, Any] | None:
        """Select next item according to weighted fair schedule.

        1. Inspects tiers with remaining quota in preferred order (high -> normal -> low).
        2. If preferred tier has remaining quota and items, pops and returns item.
        3. If non-empty tiers exist but their quota was exhausted, resets quota cycle.
        4. If all queues are empty, returns None.
        """
        self._reset_weights_if_exhausted()

        # Step 1: Follow remaining quota order
        for tier in PRIORITY_TIERS:
            if self._remaining.get(tier, 0) > 0 and not self._queues[tier].empty():
                item = self._queues[tier].get_nowait()
                self._remaining[tier] -= 1
                self._processed_counts[tier] += 1
                return tier, item

        # Step 2: Quota for non-empty queues was exhausted in this cycle — reset and pick
        self._remaining = dict(self.weights)
        for tier in PRIORITY_TIERS:
            if not self._queues[tier].empty():
                item = self._queues[tier].get_nowait()
                self._remaining[tier] -= 1
                self._processed_counts[tier] += 1
                return tier, item

        return None

    async def get_next(self) -> tuple[str, Any]:
        """Await and return the next item according to the weighted schedule."""
        while True:
            selected = self.select_next()
            if selected is not None:
                return selected
            self._notify_event.clear()
            selected = self.select_next()
            if selected is not None:
                return selected
            await self._notify_event.wait()
