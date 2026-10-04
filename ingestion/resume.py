"""Recover the stream position after a restart, from Kafka itself.

Every message the producer writes carries the upstream position in its
`last_event_id` header (ADR-0007). On startup we read the newest message of each
partition and resume from the most recent one, so the service needs no state
store of its own.
"""

import logging
import time
from collections.abc import Iterable

from confluent_kafka import Consumer, KafkaError, KafkaException, Message, TopicPartition

from ingestion.config import Settings

log = logging.getLogger(__name__)

HEADER = "last_event_id"


def pick_latest(tails: Iterable[tuple[int, str]]) -> str:
    """From (produce timestamp in ms, event id) pairs, return the newest event id.

    A single producer writes in stream order, so the message produced last holds
    the furthest position. Returns "" when there is nothing to resume from.
    """
    candidates = [(timestamp, event_id) for timestamp, event_id in tails if event_id]
    if not candidates:
        return ""
    return max(candidates)[1]


def find_resume_position(settings: Settings, timeout_seconds: float = 15.0) -> str:
    """Return the `Last-Event-ID` to resume from, or "" to start from now."""
    consumer = Consumer(
        {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            # Never commits and only uses assign(), so the group is just a label.
            "group.id": "wikipulse-ingestion-resume",
            "enable.auto.commit": False,
            "enable.partition.eof": True,
        }
    )
    try:
        last_offsets = _last_offsets(consumer, [settings.raw_topic, settings.dlq_topic])
        if not last_offsets:
            return ""
        consumer.assign(last_offsets)
        return pick_latest(_read_one_per_partition(consumer, len(last_offsets), timeout_seconds))
    finally:
        consumer.close()


def _last_offsets(consumer: Consumer, topics: list[str]) -> list[TopicPartition]:
    """The offset of the newest message in every non-empty partition."""
    result = []
    for topic in topics:
        metadata = consumer.list_topics(topic, timeout=10).topics[topic]
        if metadata.error is not None:
            log.warning("topic unavailable", extra={"topic": topic, "error": str(metadata.error)})
            continue
        for partition in metadata.partitions:
            low, high = consumer.get_watermark_offsets(TopicPartition(topic, partition), timeout=10)
            if high > low:
                result.append(TopicPartition(topic, partition, high - 1))
    return result


def _read_one_per_partition(
    consumer: Consumer, partitions: int, timeout_seconds: float
) -> list[tuple[int, str]]:
    tails: list[tuple[int, str]] = []
    seen: set[tuple[str, int]] = set()
    deadline = time.monotonic() + timeout_seconds
    while len(seen) < partitions and time.monotonic() < deadline:
        message = consumer.poll(1.0)
        if message is None:
            continue
        error = message.error()
        if error is not None:
            if error.code() == KafkaError._PARTITION_EOF:
                continue
            raise KafkaException(error)
        topic, partition = message.topic(), message.partition()
        if topic is None or partition is None or (topic, partition) in seen:
            continue
        seen.add((topic, partition))
        tails.append((message.timestamp()[1], _event_id(message)))
    return tails


def _event_id(message: Message) -> str:
    headers = message.headers()
    if not isinstance(headers, list):
        return ""
    for key, value in headers:
        if key == HEADER and isinstance(value, bytes):
            return value.decode()
    return ""
