"""Record the stream to a file and replay it later.

A recording is a text file with one JSON object per line:

    {"id": "<stream position>", "data": "<event payload, exactly as received>"}

The payload is kept as a string, so broken payloads can be recorded and replayed
too. A path ending in `.gz` is compressed.

Replay feeds the same code path as the live stream, so the same validation,
keys and dead-lettering apply. It makes runs repeatable and lets us push far
more load than the live stream offers.

Recordings are ordered by event time (see `record`).
"""

import asyncio
import gzip
import heapq
import json
import time
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Literal

from ingestion.sse import StreamMessage


def open_text(path: Path, mode: Literal["r", "w"]) -> IO[str]:
    if path.suffix == ".gz":
        return gzip.open(path, "rt" if mode == "r" else "wt", encoding="utf-8")
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
    return _time_and_topic(data)[0]


def _time_and_topic(data: str) -> tuple[datetime | None, str]:
    """`meta.dt` and `meta.topic` of an event. Unreadable parts come back as None / ""."""
    try:
        meta = json.loads(data)["meta"]
        topic = meta.get("topic")
        return datetime.fromisoformat(meta["dt"]), topic if isinstance(topic, str) else ""
    except (ValueError, KeyError, TypeError, AttributeError):
        return None, ""


def _upstream_topics(event_id: str) -> set[str]:
    """The upstream topics behind the stream, as listed in a message id."""
    try:
        return {entry["topic"] for entry in json.loads(event_id)}
    except (ValueError, KeyError, TypeError):
        return set()


async def record(
    source: AsyncIterator[StreamMessage],
    path: Path,
    *,
    seconds: float | None = None,
    max_events: int | None = None,
    until: datetime | None = None,
    margin_seconds: float = 60.0,
    idle_grace_seconds: float = 15.0,
) -> int:
    """Write messages from `source` to `path`, ordered by event time.

    The stream is fed by more than one upstream topic. When it serves history,
    each topic arrives in time order but the topics are not merged: a quiet
    topic can run hours ahead of a busy one. So each topic is written to its own
    part file, and the parts are merged by event time at the end.

    Stops after `seconds`, after `max_events`, or at `until`:
    events at or after `until` are not written, and recording ends once every
    upstream topic has gone `margin_seconds` past it. If only some topics get
    there (a quiet topic may have nothing newer), it ends after
    `idle_grace_seconds` without anything left to write.

    Returns the number of messages written.
    """
    deadline = time.monotonic() + seconds if seconds is not None else None
    parts_dir = path.parent / (path.name + ".parts")
    parts_dir.mkdir(parents=True, exist_ok=True)
    parts: dict[str, IO[str]] = {}
    last_key: dict[str, int] = {}
    expected: set[str] = set()
    passed: set[str] = set()
    last_write = time.monotonic()
    count = 0
    try:
        async for message in source:
            produced, topic = _time_and_topic(message.data)
            expected = _upstream_topics(message.event_id) or expected | {topic}
            now = time.monotonic()

            if until is not None and produced is not None and produced >= until:
                if (produced - until).total_seconds() >= margin_seconds:
                    passed.add(topic)
            else:
                if topic not in parts:
                    parts[topic] = (parts_dir / f"{len(parts)}.part").open("w", encoding="utf-8")
                # An event with no readable time keeps its place: it sorts with
                # the event before it.
                if produced is not None:
                    last_key[topic] = int(produced.timestamp() * 1_000_000)
                parts[topic].write(f"{last_key.get(topic, 0):020d}	{encode(message)}
")
                count += 1
                last_write = now

            if max_events is not None and count >= max_events:
                break
            if deadline is not None and now >= deadline:
                break
            if passed and (expected <= passed or now - last_write >= idle_grace_seconds):
                break
    finally:
        # Also runs when interrupted, so a partial recording is still usable.
        for part in parts.values():
            part.close()
        _merge_parts(parts_dir, path)
    return count


_KEY_WIDTH = 20


def _merge_parts(parts_dir: Path, path: Path) -> None:
    part_paths = sorted(parts_dir.glob("*.part"))
    files = [part.open("r", encoding="utf-8") for part in part_paths]
    try:
        with open_text(path, "w") as out:
            for line in heapq.merge(*files, key=lambda line: line[:_KEY_WIDTH]):
                out.write(line[_KEY_WIDTH + 1 :])
    finally:
        for file in files:
            file.close()
    for part in part_paths:
        part.unlink()
    parts_dir.rmdir()


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
