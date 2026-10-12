"""Outbox Relay background service runner and CLI entrypoint (FEAT-02)."""
from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import time
from datetime import datetime, timezone
from typing import Callable

from app.config import get_settings
from app.core.rabbitmq import publish_task
from app.database import AsyncSessionLocal
from app.outbox.cleanup import prune_published_outbox
from app.outbox.metrics import (
    outbox_message_age_seconds,
    outbox_publish_latency_seconds,
)
from app.outbox.service import (
    claim_pending_events,
    mark_failed,
    mark_published,
)

logger = logging.getLogger("outbox.relay")


class OutboxRelayService:
    """Production-grade asynchronous outbox relay service.
    
    Guarantees at-least-once message dispatch via PostgreSQL SKIP LOCKED
    and safe exponential backoff on broker network failures.
    """

    def __init__(
        self,
        session_factory: Callable = AsyncSessionLocal,
        poll_interval_seconds: float | None = None,
        batch_size: int | None = None,
        retention_hours: int | None = None,
        cleanup_interval_seconds: int | None = None,
    ):
        settings = get_settings()
        self.session_factory = session_factory
        self.poll_interval = (
            poll_interval_seconds
            if poll_interval_seconds is not None
            else settings.outbox_poll_interval_seconds
        )
        self.batch_size = (
            batch_size if batch_size is not None else settings.outbox_batch_size
        )
        self.retention_hours = (
            retention_hours
            if retention_hours is not None
            else settings.outbox_retention_hours
        )
        self.cleanup_interval = (
            cleanup_interval_seconds
            if cleanup_interval_seconds is not None
            else settings.outbox_cleanup_interval_seconds
        )
        self.running = False
        self._last_cleanup_time = 0.0

    async def run_once(self) -> int:
        """Claim a batch of pending events using SKIP LOCKED and relay to RabbitMQ.

        Holds row locks across the entire batch to prevent duplicate claims by
        concurrent relay runners, committing all updates atomically at the end.
        """
        drained_count = 0
        async with self.session_factory() as db:
            try:
                events = await claim_pending_events(db, batch_size=self.batch_size)
                if not events:
                    return 0

                for event in events:
                    start_publish = time.monotonic()
                    try:
                        await publish_task(
                            task_id=str(event.task_id),
                            task_type=event.task_type,
                            priority=event.priority,
                            traceparent=event.traceparent,
                        )
                        publish_duration = time.monotonic() - start_publish
                        outbox_publish_latency_seconds.observe(publish_duration)

                        await mark_published(db, event.id, commit=False)
                        drained_count += 1

                        if event.created_at:
                            age = (
                                datetime.now(timezone.utc) - event.created_at
                            ).total_seconds()
                            outbox_message_age_seconds.observe(max(0.0, age))

                    except Exception as pub_exc:
                        await mark_failed(db, event.id, error=str(pub_exc), commit=False)
                        logger.warning(
                            "Relay publication error for event %s (task %s): %s",
                            event.id,
                            event.task_id,
                            pub_exc,
                        )

                await db.commit()

            except Exception as batch_exc:
                await db.rollback()
                logger.error("Error claiming or processing outbox batch: %s", batch_exc)

        return drained_count

    async def maybe_cleanup(self) -> None:
        """Periodically prune aged published outbox entries."""
        now = time.monotonic()
        if now - self._last_cleanup_time >= self.cleanup_interval:
            self._last_cleanup_time = now
            async with self.session_factory() as db:
                try:
                    await prune_published_outbox(
                        db, retention_hours=self.retention_hours
                    )
                except Exception as exc:
                    logger.warning("Retention cleanup error: %s", exc)

    async def start(self) -> None:
        """Run the continuous relay and cleanup polling loop."""
        self.running = True
        logger.info(
            "Outbox Relay started (poll_interval=%.2fs, batch_size=%d, retention=%dh).",
            self.poll_interval,
            self.batch_size,
            self.retention_hours,
        )
        while self.running:
            try:
                processed = await self.run_once()
                await self.maybe_cleanup()

                if processed == 0 and self.running:
                    await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as loop_exc:
                logger.error("Unexpected error in relay loop: %s", loop_exc)
                if self.running:
                    await asyncio.sleep(self.poll_interval)

        logger.info("Outbox Relay shutdown cleanly.")

    def stop(self) -> None:
        """Signal relay loop to stop gracefully."""
        self.running = False


async def main():
    """CLI runner entrypoint for python -m app.outbox.relay."""
    parser = argparse.ArgumentParser(description="TaskForge Outbox Relay Runner")
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=None,
        help="Polling sleep interval in seconds when outbox is empty",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Maximum outbox rows to claim per batch",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    relay = OutboxRelayService(
        poll_interval_seconds=args.poll_interval,
        batch_size=args.batch_size,
    )

    loop = asyncio.get_running_loop()

    def _handle_shutdown():
        logger.info("Shutdown signal received.")
        relay.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_shutdown)
        except NotImplementedError:
            # Signal handling on Windows proactor loop fallback
            pass

    try:
        await relay.start()
    except KeyboardInterrupt:
        relay.stop()


if __name__ == "__main__":
    asyncio.run(main())
