import asyncio
import json
from collections import Counter
from pathlib import Path
from typing import Any, cast

import pytest

from ingestion import main as ingestion_main
from ingestion import recording
from ingestion.config import Settings, Topics
from ingestion.main import handle, run_replay
from ingestion.publisher import Headers, Publisher
from ingestion.sse import StreamMessage

# model_construct() gives the defaults without reading the environment or .env.
DEFAULTS = Settings.model_construct()


class FakePublisher:
    def __init__(self) -> None:
        self.sent: list[tuple[str, bytes, bytes | None, Headers]] = []
        self.delivered = 0
        self.failed = 0

    def publish(self, topic: str, value: bytes, key: bytes | None, headers: Headers) -> None:
        self.sent.append((topic, value, key, headers))

    def close(self) -> int:
        return 0


def run_handle(
    data: str, topics: Topics = DEFAULTS.live_topics
) -> tuple[FakePublisher, Counter[str]]:
    publisher = FakePublisher()
    stats: Counter[str] = Counter()
    message = StreamMessage(event_id="pos-1", data=data)
    handle(message, cast(Publisher, publisher), topics, stats)
    return publisher, stats


def event_json(**meta: Any) -> str:
    event = {
        "meta": {"id": "a", "dt": "2026-10-04T07:38:15Z", **meta},
        "type": "edit",
        "wiki": "enwiki",
        "title": "X",
    }
    return json.dumps(event)


def test_valid_event_goes_to_the_raw_topic_unchanged() -> None:
    data = event_json()
    publisher, stats = run_handle(data)

    headers: Headers = [("last_event_id", b"pos-1")]
    assert publisher.sent == [("wiki.raw", data.encode(), b"enwiki:X", headers)]
    assert stats == Counter(forwarded=1)


def test_invalid_event_goes_to_the_dead_letter_topic_with_a_reason() -> None:
    publisher, stats = run_handle("{not json")

    headers: Headers = [("last_event_id", b"pos-1"), ("error", b"invalid_json")]
    assert publisher.sent == [("wiki.dlq", b"{not json", None, headers)]
    assert stats == Counter(dead_lettered=1)


def test_canary_event_is_dropped() -> None:
    publisher, stats = run_handle(event_json(domain="canary"))

    assert publisher.sent == []
    assert stats == Counter(skipped=1)


def test_messages_go_to_the_topics_they_are_given() -> None:
    topics = Topics(raw="some.raw", dlq="some.dlq")

    valid, _ = run_handle(event_json(), topics)
    invalid, _ = run_handle("{not json", topics)

    assert [sent[0] for sent in valid.sent] == ["some.raw"]
    assert [sent[0] for sent in invalid.sent] == ["some.dlq"]


def test_a_replay_never_writes_to_the_live_topics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The live producer resumes from the newest message in the live topics.

    A replayed message carries the position of its recording, so one replayed
    message in a live topic would move the resume point (ADR-0008).
    """
    path = tmp_path / "recording.jsonl"
    messages = [
        StreamMessage(event_id="recorded-1", data=event_json()),
        StreamMessage(event_id="recorded-2", data="{not json"),
    ]
    path.write_text("".join(recording.encode(item) + chr(10) for item in messages))
    publisher = FakePublisher()
    monkeypatch.setattr(ingestion_main, "Publisher", lambda settings: publisher)

    asyncio.run(run_replay(DEFAULTS, path, speed=0))

    assert [sent[0] for sent in publisher.sent] == ["wiki.replay", "wiki.replay.dlq"]
    live = {DEFAULTS.raw_topic, DEFAULTS.dlq_topic}
    assert not live & {sent[0] for sent in publisher.sent}
