import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ingestion.recording import event_time, read_recording, record, replay
from ingestion.sse import StreamMessage


def message(event_id: str, second: int, **extra: object) -> StreamMessage:
    """A stream message whose event was produced at 10:00:<second>."""
    event = {"meta": {"dt": f"2026-10-04T10:00:{second:02d}.000Z"}, **extra}
    return StreamMessage(event_id=event_id, data=json.dumps(event))


async def as_stream(messages: list[StreamMessage]) -> AsyncIterator[StreamMessage]:
    for item in messages:
        yield item


def write(
    path: Path,
    messages: list[StreamMessage],
    *,
    max_events: int | None = None,
    until: datetime | None = None,
) -> int:
    return asyncio.run(record(as_stream(messages), path, max_events=max_events, until=until))


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


def test_record_stops_when_caught_up(tmp_path: Path) -> None:
    """Recording history ends at the first event at or after `until`."""
    path = tmp_path / "rec.jsonl"
    until = datetime(2026, 10, 4, 10, 0, 2, tzinfo=UTC)

    assert write(path, [message(f"pos-{i}", i) for i in range(5)], until=until) == 3


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
