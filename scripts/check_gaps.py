"""Check the raw topic for lost and duplicated events.

Every Wikimedia event carries its position in Wikimedia's own Kafka
(`meta.topic`, `meta.partition`, `meta.offset`). Those offsets are consecutive,
so after reading our raw topic we can tell exactly what is missing or repeated.

Usage: `make check-gaps` (exits with status 1 if any event is missing).
"""

import json
import sys
from collections import defaultdict

from confluent_kafka import OFFSET_BEGINNING, Consumer, KafkaError, KafkaException, TopicPartition

from ingestion.config import Settings


def read_upstream_offsets(settings: Settings) -> dict[tuple[str, int], list[int]]:
    """Read the whole raw topic and group upstream offsets by upstream partition."""
    consumer = Consumer(
        {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "group.id": "wikipulse-check-gaps",
            "enable.auto.commit": False,
            "enable.partition.eof": True,
        }
    )
    offsets: dict[tuple[str, int], list[int]] = defaultdict(list)
    try:
        topic = settings.raw_topic
        partitions = consumer.list_topics(topic, timeout=10).topics[topic].partitions
        consumer.assign([TopicPartition(topic, p, OFFSET_BEGINNING) for p in partitions])
        finished: set[int] = set()
        while len(finished) < len(partitions):
            message = consumer.poll(5.0)
            if message is None:
                continue
            error = message.error()
            if error is not None:
                if error.code() == KafkaError._PARTITION_EOF:
                    partition = message.partition()
                    if partition is not None:
                        finished.add(partition)
                    continue
                raise KafkaException(error)
            value = message.value()
            if not isinstance(value, bytes):
                continue
            meta = json.loads(value)["meta"]
            offsets[(meta["topic"], meta["partition"])].append(meta["offset"])
    finally:
        consumer.close()
    return offsets


def main() -> int:
    offsets = read_upstream_offsets(Settings())
    if not offsets:
        print("raw topic is empty")
        return 0

    missing_total = 0
    for (topic, partition), seen in sorted(offsets.items()):
        unique = set(seen)
        first, last = min(unique), max(unique)
        missing = (last - first + 1) - len(unique)
        missing_total += missing
        print(
            f"{topic}[{partition}]: offsets {first}..{last}, "
            f"{len(seen)} messages, {len(seen) - len(unique)} duplicates, {missing} missing"
        )
    return 1 if missing_total else 0


if __name__ == "__main__":
    sys.exit(main())
