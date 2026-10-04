"""Entry point: read the Wikimedia stream and publish every event to Kafka."""

import asyncio
import logging
import signal
import time
from collections import Counter
from contextlib import suppress

from ingestion.config import Settings
from ingestion.events import Invalid, Skipped, Valid, classify
from ingestion.log import configure_logging
from ingestion.publisher import Headers, Publisher
from ingestion.sse import StreamMessage, stream_events

log = logging.getLogger("ingestion")


def handle(
    message: StreamMessage, publisher: Publisher, settings: Settings, stats: Counter[str]
) -> None:
    """Route one stream message: raw topic, dead-letter topic, or drop."""
    verdict = classify(message.data)
    value = message.data.encode()
    # The upstream position travels with every message, so a later version can
    # recover the resume point from Kafka itself after a restart.
    headers: Headers = [("last_event_id", message.event_id.encode())]

    match verdict:
        case Valid(key=key):
            publisher.publish(settings.raw_topic, value, key, headers)
            stats["forwarded"] += 1
        case Invalid(reason=reason):
            publisher.publish(
                settings.dlq_topic, value, None, [*headers, ("error", reason.encode())]
            )
            stats["dead_lettered"] += 1
        case Skipped():
            stats["skipped"] += 1


async def pump(settings: Settings, publisher: Publisher, stats: Counter[str]) -> None:
    last_report = time.monotonic()
    async for message in stream_events(settings):
        handle(message, publisher, settings, stats)
        now = time.monotonic()
        if now - last_report >= settings.stats_interval_seconds:
            report(stats, publisher)
            last_report = now


def report(stats: Counter[str], publisher: Publisher) -> None:
    log.info(
        "ingestion stats",
        extra={**stats, "delivered": publisher.delivered, "delivery_failed": publisher.failed},
    )


async def run(settings: Settings) -> None:
    publisher = Publisher(settings)
    stats: Counter[str] = Counter()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    log.info(
        "ingestion starting",
        extra={"stream_url": settings.stream_url, "raw_topic": settings.raw_topic},
    )
    pump_task = asyncio.create_task(pump(settings, publisher, stats))
    stop_task = asyncio.create_task(stop.wait())
    try:
        await asyncio.wait({pump_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in (pump_task, stop_task):
            task.cancel()
        with suppress(asyncio.CancelledError):
            await pump_task
        # Graceful shutdown: do not exit with messages still in the local queue.
        unsent = publisher.close()
        report(stats, publisher)
        log.info("ingestion stopped", extra={"unsent": unsent})


def main() -> None:
    settings = Settings()
    configure_logging(settings.log_level)
    asyncio.run(run(settings))


if __name__ == "__main__":
    main()
