"""Entry point.

python -m ingestion                      live stream -> Kafka
python -m ingestion record --out FILE    live stream -> file
python -m ingestion replay FILE          file -> Kafka (the replay topics)
"""

import argparse
import asyncio
import logging
import signal
import time
from collections import Counter
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

from ingestion import recording
from ingestion.config import Settings, Topics
from ingestion.events import Invalid, Skipped, Valid, classify
from ingestion.log import configure_logging
from ingestion.publisher import Headers, Publisher
from ingestion.resume import find_resume_position
from ingestion.sse import StreamMessage, stream_events

log = logging.getLogger("ingestion")


def handle(
    message: StreamMessage, publisher: Publisher, topics: Topics, stats: Counter[str]
) -> None:
    """Route one stream message: raw topic, dead-letter topic, or drop."""
    verdict = classify(message.data)
    value = message.data.encode()
    # The upstream position travels with every message, so the producer can
    # recover the resume point from Kafka itself after a restart.
    headers: Headers = [("last_event_id", message.event_id.encode())]

    match verdict:
        case Valid(key=key):
            publisher.publish(topics.raw, value, key, headers)
            stats["forwarded"] += 1
        case Invalid(reason=reason):
            publisher.publish(topics.dlq, value, None, [*headers, ("error", reason.encode())])
            stats["dead_lettered"] += 1
        case Skipped():
            stats["skipped"] += 1


async def pump(
    source: AsyncIterator[StreamMessage],
    settings: Settings,
    topics: Topics,
    publisher: Publisher,
    stats: Counter[str],
) -> None:
    last_report = time.monotonic()
    async for message in source:
        handle(message, publisher, topics, stats)
        now = time.monotonic()
        if now - last_report >= settings.stats_interval_seconds:
            report(stats, publisher)
            last_report = now


def report(stats: Counter[str], publisher: Publisher) -> None:
    log.info(
        "ingestion stats",
        extra={**stats, "delivered": publisher.delivered, "delivery_failed": publisher.failed},
    )


async def publish_from(
    source: AsyncIterator[StreamMessage], settings: Settings, topics: Topics
) -> None:
    """Publish every message from `source` to `topics` until it ends or is told to stop."""
    publisher = Publisher(settings)
    stats: Counter[str] = Counter()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    started = time.monotonic()
    pump_task = asyncio.create_task(pump(source, settings, topics, publisher, stats))
    stop_task = asyncio.create_task(stop.wait())
    try:
        await asyncio.wait({pump_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in (pump_task, stop_task):
            task.cancel()
        outcome, _ = await asyncio.gather(pump_task, stop_task, return_exceptions=True)
        # Graceful shutdown: do not exit with messages still in the local queue.
        unsent = publisher.close()
        report(stats, publisher)
        elapsed = time.monotonic() - started
        log.info(
            "ingestion stopped",
            extra={
                "unsent": unsent,
                "seconds": round(elapsed, 1),
                "events_per_second": round(sum(stats.values()) / elapsed, 1),
            },
        )
    if isinstance(outcome, Exception):
        raise outcome


async def run_live(settings: Settings) -> None:
    # Continue from where the previous run stopped, so a restart loses nothing.
    start_event_id = find_resume_position(settings) if settings.resume_on_start else ""
    log.info(
        "ingestion starting",
        extra={
            "source": settings.stream_url,
            "raw_topic": settings.raw_topic,
            "resume_from": start_event_id or "now",
        },
    )
    await publish_from(
        stream_events(settings, start_event_id=start_event_id), settings, settings.live_topics
    )


async def run_replay(settings: Settings, path: Path, speed: float) -> None:
    # A replay has its own topics. Its messages carry the recording's stream
    # position, and in the live topics the live producer would resume from it.
    topics = settings.replay_topics
    log.info(
        "replay starting",
        extra={"source": str(path), "raw_topic": topics.raw, "speed": speed or "max"},
    )
    await publish_from(recording.replay(path, speed=speed), settings, topics)


async def run_record(
    settings: Settings,
    path: Path,
    seconds: float | None,
    max_events: int | None,
    since: datetime | None,
    until: datetime | None,
) -> None:
    # Recording history stops by itself once it has caught up with the present.
    if since is not None and until is None:
        until = recording.minutes_ago(0)
    log.info(
        "recording starting",
        extra={
            "out": str(path),
            "since": since.isoformat() if since else "now",
            "until": until.isoformat() if until else "stopped by hand or by a limit",
        },
    )
    since_param = since.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if since else ""
    source = stream_events(settings, since=since_param)
    count = await recording.record(
        source, path, seconds=seconds, max_events=max_events, until=until
    )
    await source.aclose()
    log.info("recording finished", extra={"out": str(path), "events": count})


def utc_time(text: str) -> datetime:
    """Parse an ISO timestamp. A time with no zone is taken as UTC."""
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="ingestion", description="Wikimedia stream to Kafka")
    commands = parser.add_subparsers(dest="command")

    record = commands.add_parser("record", help="save the live stream to a file")
    record.add_argument("--out", type=Path, required=True, help="file to write (.gz compresses)")
    record.add_argument("--seconds", type=float, help="stop after this many seconds")
    record.add_argument("--max-events", type=int, help="stop after this many events")
    record.add_argument(
        "--since-minutes",
        type=float,
        help="start this many minutes in the past and stop when caught up with now",
    )
    record.add_argument(
        "--from",
        dest="since",
        type=utc_time,
        help="start at this time, e.g. 2026-09-30T10:00:00Z (Wikimedia keeps about 7 days)",
    )
    record.add_argument(
        "--to", dest="until", type=utc_time, help="stop at this time (default: now)"
    )

    replay = commands.add_parser("replay", help="publish a recorded file to Kafka")
    replay.add_argument("path", type=Path, help="recording to replay")
    replay.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="1 = original timing, 10 = ten times faster, 0 = no pacing (default: 1)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    settings = Settings()
    configure_logging(settings.log_level)
    match args.command:
        case "record":
            since = args.since
            if since is None and args.since_minutes:
                since = recording.minutes_ago(args.since_minutes)
            asyncio.run(
                run_record(settings, args.out, args.seconds, args.max_events, since, args.until)
            )
        case "replay":
            asyncio.run(run_replay(settings, args.path, args.speed))
        case _:
            asyncio.run(run_live(settings))


if __name__ == "__main__":
    main()
