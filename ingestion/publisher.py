"""Kafka producer wrapper."""

import logging

from confluent_kafka import KafkaError, Message, Producer

from ingestion.config import Settings

log = logging.getLogger(__name__)

Headers = list[tuple[str, bytes]]


class Publisher:
    def __init__(self, settings: Settings) -> None:
        self._producer = Producer(
            {
                "bootstrap.servers": settings.kafka_bootstrap_servers,
                "client.id": "wikipulse-ingestion",
                # Idempotence implies acks=all and makes broker-side retries safe:
                # a retried batch is never written twice.
                "enable.idempotence": True,
                # Wait up to 50ms to fill a batch. Costs a little latency, buys
                # much better batching and compression.
                "linger.ms": 50,
                "compression.type": "zstd",
            }
        )
        self.delivered = 0
        self.failed = 0

    def publish(self, topic: str, value: bytes, key: bytes | None, headers: Headers) -> None:
        """Queue a message for sending. Returns before the broker acknowledges it."""
        while True:
            try:
                self._producer.produce(
                    topic, value=value, key=key, headers=headers, on_delivery=self._on_delivery
                )
                break
            except BufferError:
                # Local queue is full: serve delivery callbacks until there is room.
                self._producer.poll(0.5)
        self._producer.poll(0)

    def close(self, timeout_seconds: float = 10.0) -> int:
        """Send everything still queued. Returns how many messages were left unsent."""
        return self._producer.flush(timeout_seconds)

    def _on_delivery(self, error: KafkaError | None, message: Message) -> None:
        if error is None:
            self.delivered += 1
            return
        self.failed += 1
        log.error("delivery failed", extra={"topic": message.topic(), "error": str(error)})
