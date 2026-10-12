"""Unit tests for Step 4.3: Priority anti-Starvation Fairness & Weighted Consumption."""
import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.core.rabbitmq import RabbitMQPublisher
from app.worker.consumer import declare_priority_queues, subscribe_queues
from app.worker.priority import (
    PRIORITY_TIERS,
    PriorityFairDispatcher,
    get_priority_queue_name,
    get_priority_tier,
)



def test_priority_tier_classification():
    """Verify integer priority levels map to high, normal, low tiers."""
    # High: >= 7
    assert get_priority_tier(10) == "high"
    assert get_priority_tier(8) == "high"
    assert get_priority_tier(7) == "high"

    # Normal: 3..6
    assert get_priority_tier(6) == "normal"
    assert get_priority_tier(5) == "normal"
    assert get_priority_tier(3) == "normal"

    # Low: < 3
    assert get_priority_tier(2) == "low"
    assert get_priority_tier(1) == "low"
    assert get_priority_tier(0) == "low"
    assert get_priority_tier(-5) == "low"

    # Queue names
    assert get_priority_queue_name(9) == "tasks.high"
    assert get_priority_queue_name(4) == "tasks.normal"
    assert get_priority_queue_name(0) == "tasks.low"


def test_weighted_fair_queue_distribution():
    """Verify 60% high, 30% normal, 10% low ratio over repeated cycles."""
    dispatcher = PriorityFairDispatcher(weights={"high": 6, "normal": 3, "low": 1})

    # Enqueue 30 items: 18 high, 9 normal, 3 low (exactly 3 full cycles)
    for i in range(18):
        dispatcher.enqueue(f"high-{i}", tier="high")
    for i in range(9):
        dispatcher.enqueue(f"normal-{i}", tier="normal")
    for i in range(3):
        dispatcher.enqueue(f"low-{i}", tier="low")

    # In each cycle of 10 items, verify 6 high, 3 normal, 1 low
    for cycle in range(3):
        cycle_items = [dispatcher.select_next() for _ in range(10)]
        tiers = [item[0] for item in cycle_items]
        assert tiers.count("high") == 6, f"Cycle {cycle} high count mismatch"
        assert tiers.count("normal") == 3, f"Cycle {cycle} normal count mismatch"
        assert tiers.count("low") == 1, f"Cycle {cycle} low count mismatch"

    # All queues should now be empty
    assert dispatcher.select_next() is None


def test_anti_starvation_guarantee_under_high_priority_surge():
    """Verify low-priority tasks are not starved during sustained high-priority traffic."""
    dispatcher = PriorityFairDispatcher(weights={"high": 6, "normal": 3, "low": 1})

    # Surge: 50 high tasks and 2 low tasks, 0 normal tasks
    for i in range(50):
        dispatcher.enqueue(f"high-{i}", tier="high")
    dispatcher.enqueue("low-0", tier="low")
    dispatcher.enqueue("low-1", tier="low")

    selected = []
    # Consume 14 items
    for _ in range(14):
        item = dispatcher.select_next()
        if item:
            selected.append(item)

    selected_tiers = [s[0] for s in selected]

    # In first block: 6 high, then (normal is empty so falls through to) 1 low!
    # Low task MUST be processed and not starved behind 50 high tasks.
    assert "low" in selected_tiers[:8]
    assert selected_tiers.count("low") == 2


def test_fallthrough_when_high_queue_empty():
    """When high queue is empty, normal and low tasks are served without delay."""
    dispatcher = PriorityFairDispatcher()

    # Enqueue only normal and low
    dispatcher.enqueue("normal-1", tier="normal")
    dispatcher.enqueue("low-1", tier="low")

    tier1, item1 = dispatcher.select_next()
    assert tier1 == "normal"
    assert item1 == "normal-1"

    tier2, item2 = dispatcher.select_next()
    assert tier2 == "low"
    assert item2 == "low-1"

    assert dispatcher.select_next() is None


@pytest.mark.asyncio
async def test_async_get_next_waits_for_enqueue():
    """Verify get_next asynchronously waits when all queues are empty."""
    dispatcher = PriorityFairDispatcher()

    async def delayed_enqueue():
        await asyncio.sleep(0.05)
        dispatcher.enqueue("delayed-task", priority=8)

    asyncio.create_task(delayed_enqueue())
    tier, item = await dispatcher.get_next()
    assert tier == "high"
    assert item == "delayed-task"


@pytest.mark.asyncio
async def test_publish_routes_across_priority_queues():
    """Verify RabbitMQPublisher routes across tasks.high/normal/low when route_by_priority is set."""
    publisher = RabbitMQPublisher()
    publisher._connection = AsyncMock()
    publisher._connection.is_closed = False
    publisher._channel = AsyncMock()
    publisher._channel.is_closed = False
    mock_exchange = AsyncMock()
    publisher._exchange = mock_exchange

    # Priority 9 -> tasks.high
    await publisher.publish(
        task_id="t-high",
        task_type="email_send",
        priority=9,
        route_by_priority=True,
    )
    assert mock_exchange.publish.call_args[1]["routing_key"] == "tasks.high"
    headers = mock_exchange.publish.call_args[0][0].headers
    assert headers["x-priority-tier"] == "high"
    assert headers["x-priority"] == 9

    # Priority 5 -> tasks.normal
    await publisher.publish(
        task_id="t-normal",
        task_type="email_send",
        priority=5,
        route_by_priority=True,
    )
    assert mock_exchange.publish.call_args[1]["routing_key"] == "tasks.normal"
    assert mock_exchange.publish.call_args[0][0].headers["x-priority-tier"] == "normal"

    # Priority 1 -> tasks.low
    await publisher.publish(
        task_id="t-low",
        task_type="email_send",
        priority=1,
        route_by_priority=True,
    )
    assert mock_exchange.publish.call_args[1]["routing_key"] == "tasks.low"
    assert mock_exchange.publish.call_args[0][0].headers["x-priority-tier"] == "low"


@pytest.mark.asyncio
async def test_declare_priority_queues_creates_x_max_priority():
    """Verify declare_priority_queues declares tasks.high/normal/low with x-max-priority: 10."""
    channel = AsyncMock()
    exchange = AsyncMock()

    queues = await declare_priority_queues(channel, exchange, task_types=["email_send"])
    assert set(queues.keys()) == set(PRIORITY_TIERS)
    assert len(channel.declare_queue.call_args_list) == 3

    for call in channel.declare_queue.call_args_list:
        q_name, kwargs = call[0][0], call[1]
        assert q_name in ("tasks.high", "tasks.normal", "tasks.low")
        assert kwargs["arguments"]["x-max-priority"] == 10
        assert kwargs["arguments"]["x-dead-letter-routing-key"] == f"{q_name}.dlq"


@pytest.mark.asyncio
async def test_subscribe_queues_with_priority_queues():
    """Verify subscribe_queues includes priority queues when include_priority_queues is True."""
    channel = AsyncMock()
    exchange = AsyncMock()
    publisher = MagicMock()
    publisher.channel = channel
    publisher.exchange = exchange

    queue = AsyncMock()
    channel.declare_queue.return_value = queue
    queue.consume.return_value = "tag-x"

    consumers = await subscribe_queues(
        publisher=publisher,
        task_types=["email_send"],
        include_priority_queues=True,
    )

    # 1 task type + 3 priority queues = 4 consumers
    assert len(consumers) == 4
