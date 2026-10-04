"""Record the stream to a file and replay it later.

A recording is a text file with one JSON object per line:

    {"id": "<stream position>", "data": "<event payload, exactly as received>"}

The payload is kept as a string, so broken payloads can be recorded and replayed
too. A path ending in `.gz` is compressed.

Replay feeds the same code path as the live stream, so the same validation,
keys and dead-lettering apply. It makes runs repeatable and lets us push far
more load than the live stream offers.
"""

import asyncio
import gzip
import json
import time
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import IO

from ingestion.sse import StreamMessage


def open_text(path: Path, mode: str) -> IO[str]:
    if path.suffix == ".gz":
        return gzip.open(path, mode + "t", encoding="utf-8")
    return path.open(mode, encoding="utf-8")


def encode(message: StreamMessage) -> str:
    return json.dumps({"id": message.event_id, "data": message.data}, ensure_ascii=False)


def decode(line: str) -> StreamMessage:
    record = json.loads(line)
    return StreamMessage(event_id=record["id"], data=record["data"])


def read_recording(path: Path) -> Iterator[StreamMessage]:
    with open_text(path, "r") as file:
        for line in file:
            if line.strip():
                yield decode(line)


def event_time(data: str) -> datetime | None:
    """When the event was produced upstream (`meta.dt`), or None if unreadable."""
    try:
        return datetime.fromisoformat(json.loads(data)["meta"]["dt"])
    except (ValueError, KeyError, TypeError):
        return None


async def record(
    source: AsyncIterator[StreamMessage],
    path: Path,
    *,
    seconds: float | None = None,
    max_events: int | None = None,
    until: datetime | None = None,
) -> int:
    """Write messages from `source` to `path` until a limit is reached.

    `until` stops once an event at or after that time arrives. It is used when
    recording history, to stop when the stream has caught up with the present.
    Returns the number of messages written.
    """
    deadline = time.monotonic() + seconds if seconds is not None else None
    count = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with open_text(path, "w") as file:
        async for message in source:
            file.write(encode(message) + "\n")
            count += 1
            if max_events is not None and count >= max_events:
                break
            if deadline is not None and time.monotonic() >= deadline:
                break
            if until is not None:
                produced = event_time(message.data)
                if produced is not None and produced >= until:
                    break
    return count


async def replay(
    path: Path,
    *,
    speed: float = 1.0,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> AsyncGenerator[StreamMessage, None]:
    """Yield a recording's messages, paced by their original event times.

    `speed` 1.0 reproduces the original timing, 10.0 is ten times faster, and
    0 means no pacing at all (as fast as the consumer can take them). Event
    times are not rewritten, so every replay produces identical data.

    `clock` and `sleep` exist so tests can control time.
    """
    first_event: datetime | None = None
    started = clock()
    for message in read_recording(path):
        if speed > 0:
            produced = event_time(message.data)
            if produced is not None:
                if first_event is None:
                    first_event = produced
                # Pace against a fixed schedule rather than sleeping between
                # events, so processing time does not make the replay drift.
                due = started + (produced - first_event).total_seconds() / speed
                wait = due - clock()
                if wait > 0:
                    await sleep(wait)
        yield message


def minutes_ago(minutes: float) -> datetime:
    return datetime.fromtimestamp(time.time() - minutes * 60, UTC)
