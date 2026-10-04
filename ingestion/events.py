"""Validation and key extraction for recentchange events.

Pure logic with no I/O, so it can be unit-tested without a network or a broker.
Ingestion never filters by content (ADR-0006): every structurally valid event is forwarded.
"""

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Valid:
    """Forward to the raw topic under this key."""

    key: bytes


@dataclass(frozen=True, slots=True)
class Invalid:
    """Send to the dead-letter topic with this reason."""

    reason: str


@dataclass(frozen=True, slots=True)
class Skipped:
    """Drop silently. Used only for Wikimedia's synthetic test events."""

    reason: str


Verdict = Valid | Invalid | Skipped


def classify(raw: str) -> Verdict:
    """Decide what to do with one raw event payload.

    Only the fields every event type carries are required. Fields such as
    `revision` and `length` exist only on some types (see docs/DATA_SOURCE.md),
    so their absence is not an error.
    """
    try:
        event: Any = json.loads(raw)
    except json.JSONDecodeError:
        return Invalid("invalid_json")
    if not isinstance(event, dict):
        return Invalid("not_an_object")

    meta = event.get("meta")
    if not isinstance(meta, dict):
        return Invalid("missing_meta")
    if meta.get("domain") == "canary":
        return Skipped("canary")

    for field in ("id", "dt"):
        if not _is_non_empty_str(meta.get(field)):
            return Invalid(f"missing_meta_{field}")
    for field in ("type", "wiki"):
        if not _is_non_empty_str(event.get(field)):
            return Invalid(f"missing_{field}")

    return Valid(key=build_key(event["wiki"], event.get("title")))


def build_key(wiki: str, title: object) -> bytes:
    """Message key: `<wiki>:<title>`.

    All changes to one page share a key, so they land in one partition and stay
    in order. Page titles are high-cardinality, so load spreads evenly.
    """
    if _is_non_empty_str(title):
        return f"{wiki}:{title}".encode()
    return wiki.encode()


def _is_non_empty_str(value: object) -> bool:
    return isinstance(value, str) and value != ""
