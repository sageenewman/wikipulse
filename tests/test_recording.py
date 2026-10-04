import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ingestion.recording import event_time, read_recording, record, replay
from ingestion.sse import StreamMessage


TOPICS_ID = json.dumps([{"topic": "busy"}, {"topic": "quiet"}])


def message(event_id: str, second: int, topic: str | None = None, **extra: object) -> StreamMessage:
    """A stream message whose event was produced at 10:00:00 plus `second` seconds."""
    produced = datetime(2026, 10, 4, 10, 0, tzinfo=UTC) + timedelta(seconds=second)
    meta = {"dt": produced.strftime("%Y-%m-%dT%H:%M:%S.000Z")}
    if topic is not None:
        meta["topic"] = topic
    return StreamMessage(event_id=event_id, data=json.dumps({"meta": meta, **extra}))


def at(second: int) -> datetime:
    return datetime(2026, 10, 4, 10, 0, tzinfo=UTC) + timedelta(seconds=second)


async def as_stream(messages: list[StreamMessage]) -> AsyncIterator[StreamMessage]:
    for item in messages:
        yield item


def write(
    path: Path,
    messages: list[StreamMessage],
    *,
    max_events: int | None = None,
    until: datetime | None = None,
    margin_seconds: float = 60.0,
    idle_grace_seconds: float = 15.0,
) -> int:
    return asyncio.run(
        record(
            as_stream(messages),
            path,
            max_events=max_events,
            until=until,
            margin_seconds=margin_seconds,
            idle_grace_seconds=idle_grace_seconds,
        )
    )


def data_of(path: Path) -> list[str]:
    return [m.event_id for m in read_recording(path)]


class FakeTime:
    """A clock that only moves when something sleeps."""

    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(round(seconds, 3))
        self.now += seconds


def replay_all(path: Path, speed: float, fake: FakeTime) -> list[StreamMessage]:
    async def run() -> list[StreamMessage]:
        return [m async for m in replay(path, speed=speed, clock=fake.clock, sleep=fake.sleep)]

    return asyncio.run(run())


@pytest.mark.parametrize("name", ["rec.jsonl", "rec.jsonl.gz"])
def test_recording_round_trip(tmp_path: Path, name: str) -> None:
    messages = [message("pos-1", 0), message("pos-2", 1, title="רעידת אדמה")]
    path = tmp_path / "nested" / name

    assert write(path, messages) == 2
    assert list(read_recording(path)) == messages


def test_broken_payloads_survive_a_round_trip(tmp_path: Path) -> None:
    messages = [StreamMessage(event_id="pos-1", data='{"cut off')]
    path = tmp_path / "rec.jsonl"

    write(path, messages)

    assert list(read_recording(path)) == messages


def test_record_stops_at_max_events(tmp_path: Path) -> None:
    path = tmp_path / "rec.jsonl"

    assert write(path, [message(f"pos-{i}", i) for i in range(5)], max_events=3) == 3
    assert len(list(read_recording(path))) == 3


def test_events_at_or_after_until_are_not_written(tmp_path: Path) -> None:
    path = tmp_path / "rec.jsonl"

    assert write(path, [message(f"pos-{i}", i) for i in range(5)], until=at(2)) == 2
    assert data_of(path) == ["pos-0", "pos-1"]


def test_record_stops_once_the_stream_is_past_until(tmp_path: Path) -> None:
    path = tmp_path / "rec.jsonl"
    consumed = 0

    async def counting() -> AsyncIterator[StreamMessage]:
        nonlocal consumed
        for i in range(100):
            consumed += 1
            yield message(f"pos-{i}", i)

    count = asyncio.run(record(counting(), path, until=at(2), margin_seconds=3))

    assert count == 2
    # Stopped at the first event three seconds past `until`, not at the end.
    assert consumed == 6


def test_topics_are_merged_by_event_time(tmp_path: Path) -> None:
    """History arrives per topic, with a quiet topic running ahead of a busy one."""
    path = tmp_path / "rec.jsonl"
    received = [
        message("quiet-5", 5, "quiet"),
        message("quiet-9", 9, "quiet"),
        message("busy-0", 0, "busy"),
        message("busy-1", 1, "busy"),
        message("busy-6", 6, "busy"),
    ]

    write(path, received)

    assert data_of(path) == ["busy-0", "busy-1", "quiet-5", "busy-6", "quiet-9"]


def test_a_quiet_topic_running_ahead_does_not_end_the_recording(tmp_path: Path) -> None:
    path = tmp_path / "rec.jsonl"
    received = [
        StreamMessage(TOPICS_ID, message("", 500, "quiet").data),  # far past `until`
        StreamMessage(TOPICS_ID, message("", 0, "busy").data),
        StreamMessage(TOPICS_ID, message("", 1, "busy").data),
        StreamMessage(TOPICS_ID, message("", 200, "busy").data),  # busy topic passes too
        StreamMessage(TOPICS_ID, message("", 201, "busy").data),
    ]

    assert write(path, received, until=at(10), margin_seconds=60) == 2


def test_record_ends_after_the_grace_period_when_one_topic_never_catches_up(
    tmp_path: Path,
) -> None:
    path = tmp_path / "rec.jsonl"
    consumed = 0

    async def only_busy() -> AsyncIterator[StreamMessage]:
        nonlocal consumed
        for second in (0, 1, 200, 201, 202):
            consumed += 1
            yield StreamMessage(TOPICS_ID, message("", second, "busy").data)

    count = asyncio.run(
        record(only_busy(), path, until=at(10), margin_seconds=60, idle_grace_seconds=0)
    )

    assert count == 2
    assert consumed == 3


def test_events_without_a_time_keep_their_place(tmp_path: Path) -> None:
    path = tmp_path / "rec.jsonl"
    broken = StreamMessage(event_id="broken", data="{not json")

    write(path, [message("a", 0), broken, message("b", 1)])

    assert data_of(path) == ["a", "broken", "b"]


def test_replay_keeps_original_timing_at_speed_one(tmp_path: Path) -> None:
    path = tmp_path / "rec.jsonl"
    messages = [message("a", 0), message("b", 1), message("c", 3)]
    write(path, messages)
    fake = FakeTime()

    assert replay_all(path, 1.0, fake) == messages
    assert fake.sleeps == [1.0, 2.0]


def test_replay_speed_divides_the_waits(tmp_path: Path) -> None:
    path = tmp_path / "rec.jsonl"
    write(path, [message("a", 0), message("b", 1), message("c", 3)])
    fake = FakeTime()

    replay_all(path, 10.0, fake)

    assert fake.sleeps == [0.1, 0.2]


def test_replay_speed_zero_never_waits(tmp_path: Path) -> None:
    path = tmp_path / "rec.jsonl"
    messages = [message("a", 0), message("b", 30)]
    write(path, messages)
    fake = FakeTime()

    assert replay_all(path, 0, fake) == messages
    assert fake.sleeps == []


def test_replay_does_not_wait_for_unreadable_or_late_events(tmp_path: Path) -> None:
    path = tmp_path / "rec.jsonl"
    broken = StreamMessage(event_id="x", data="{not json")
    messages = [message("a", 5), broken, message("b", 2), message("c", 6)]
    write(path, messages)
    fake = FakeTime()

    assert replay_all(path, 1.0, fake) == messages
    # Only the wait before "c": one second after "a". The broken event and the
    # out-of-order event "b" pass straight through.
    assert fake.sleeps == [1.0]


def test_event_time() -> None:
    assert event_time(message("a", 7).data) == datetime(2026, 10, 4, 10, 0, 7, tzinfo=UTC)
    assert event_time("{not json") is None
    assert event_time("[1, 2]") is None
    assert event_time('{"meta": {"dt": "yesterday"}}') is None
