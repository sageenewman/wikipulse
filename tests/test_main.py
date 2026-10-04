import json
from collections import Counter
from typing import cast

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
    handle(message, cast(Publisher, publisher), Settings(_env_file=None), stats)
    return publisher, stats


def test_valid_event_goes_to_the_raw_topic_unchanged() -> None:
    data = json.dumps(
        {"meta": {"id": "a", "dt": "2026-10-04T07:38:15Z"}, "type": "edit", "wiki": "enwiki", "title": "X"}
    )
    publisher, stats = run_handle(data)

    assert publisher.sent == [("wiki.raw", data.encode(), b"enwiki:X", [("last_event_id", b"pos-1")])]
    assert stats == Counter(forwarded=1)


def test_invalid_event_goes_to_the_dead_letter_topic_with_a_reason() -> None:
    publisher, stats = run_handle("{not json")

    assert publisher.sent == [
        ("wiki.dlq", b"{not json", None, [("last_event_id", b"pos-1"), ("error", b"invalid_json")])
    ]
    assert stats == Counter(dead_lettered=1)


def test_canary_event_is_dropped() -> None:
    data = json.dumps({"meta": {"id": "a", "dt": "x", "domain": "canary"}, "type": "edit", "wiki": "w"})
    publisher, stats = run_handle(data)

    assert publisher.sent == []
    assert stats == Counter(skipped=1)
