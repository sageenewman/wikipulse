import json
from collections import Counter
from typing import Any, cast

from ingestion.config import Settings
from ingestion.main import handle
from ingestion.publisher import Headers, Publisher
from ingestion.sse import StreamMessage


class FakePublisher:
    def __init__(self) -> None:
        self.sent: list[tuple[str, bytes, bytes | None, Headers]] = []

    def publish(self, topic: str, value: bytes, key: bytes | None, headers: Headers) -> None:
        self.sent.append((topic, value, key, headers))


def run_handle(data: str) -> tuple[FakePublisher, Counter[str]]:
    publisher = FakePublisher()
    stats: Counter[str] = Counter()
    message = StreamMessage(event_id="pos-1", data=data)
    # model_construct() gives the defaults without reading the environment or .env.
    handle(message, cast(Publisher, publisher), Settings.model_construct(), stats)
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
