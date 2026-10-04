import json
from pathlib import Path
from typing import Any

import pytest

from ingestion.events import Invalid, Skipped, Valid, build_key, classify
from ingestion.recording import read_recording

SAMPLES = Path(__file__).parent.parent / "data" / "samples"
SAMPLE = SAMPLES / "recentchange_sample.jsonl"
BROKEN = SAMPLES / "broken_events.jsonl"


def make_event(**overrides: Any) -> dict[str, Any]:
    event: dict[str, Any] = {
        "meta": {"id": "abc-123", "dt": "2026-10-04T07:38:15.112Z", "domain": "en.wikipedia.org"},
        "type": "edit",
        "wiki": "enwiki",
        "title": "Earthquake",
    }
    event.update(overrides)
    return event


def test_valid_event_is_keyed_by_wiki_and_title() -> None:
    assert classify(json.dumps(make_event())) == Valid(key=b"enwiki:Earthquake")


def test_every_real_sample_event_is_valid() -> None:
    """The sample holds real edit, new, categorize and log events."""
    messages = list(read_recording(SAMPLE))
    assert len(messages) == 40
    assert all(isinstance(classify(message.data), Valid) for message in messages)


def test_broken_sample_covers_every_verdict() -> None:
    """The broken-events recording exists to exercise the dead-letter path."""
    verdicts = [classify(message.data) for message in read_recording(BROKEN)]
    reasons = sorted(v.reason for v in verdicts if isinstance(v, Invalid))

    assert sum(isinstance(v, Valid) for v in verdicts) == 2
    assert [v for v in verdicts if isinstance(v, Skipped)] == [Skipped("canary")]
    assert reasons == [
        "invalid_json",
        "missing_meta",
        "missing_meta_dt",
        "missing_meta_id",
        "missing_type",
        "missing_wiki",
        "not_an_object",
    ]


def test_event_without_revision_is_valid() -> None:
    """`categorize` and `log` events carry no `revision` or `length`."""
    event = make_event(type="categorize")
    assert "revision" not in event
    assert isinstance(classify(json.dumps(event)), Valid)


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ("{not json", "invalid_json"),
        ("[1, 2, 3]", "not_an_object"),
        (json.dumps({"type": "edit", "wiki": "enwiki"}), "missing_meta"),
        (json.dumps(make_event(meta={"dt": "2026-10-04T07:38:15Z"})), "missing_meta_id"),
        (json.dumps(make_event(meta={"id": "abc-123"})), "missing_meta_dt"),
        (json.dumps(make_event(type=None)), "missing_type"),
        (json.dumps(make_event(wiki="")), "missing_wiki"),
    ],
)
def test_broken_events_are_invalid(raw: str, reason: str) -> None:
    assert classify(raw) == Invalid(reason)


def test_canary_events_are_skipped() -> None:
    event = make_event(meta={"id": "abc-123", "dt": "2026-10-04T07:38:15Z", "domain": "canary"})
    assert classify(json.dumps(event)) == Skipped("canary")


def test_key_falls_back_to_wiki_when_title_is_missing() -> None:
    assert build_key("enwiki", None) == b"enwiki"
    assert build_key("enwiki", "") == b"enwiki"


def test_key_keeps_non_ascii_titles() -> None:
    assert build_key("hewiki", "רעידת אדמה") == "hewiki:רעידת אדמה".encode()
