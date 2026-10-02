# ADR-0002: Spark Structured Streaming for stream processing

- **Status:** Accepted
- **Date:** 2026-10-02

## Context
We need stateful stream processing (dedup, event-time windows, watermarks) that writes to Iceberg. Our latency requirement is seconds to minutes. We also need a batch engine for backfills and Iceberg table maintenance, and we prefer widely adopted tools with a large ecosystem.

## Decision
Use **PySpark Structured Streaming** (micro-batch).

## Alternatives considered
- **Apache Flink:** true streaming with lower latency and stronger state handling. But PyFlink is less mature, it's heavier to operate, and it would be a second engine next to the one we need for batch and maintenance.
- **Kafka Streams:** elegant, but Java-only and doesn't write to Iceberg naturally.
- **Pure-Python stream libraries (Quix Streams, Bytewax):** light, but small ecosystems and no Iceberg maintenance story.

## Consequences
- ✅ One engine for streaming, batch backfills and Iceberg maintenance.
- ✅ Large ecosystem and community.
- ⚠️ JVM memory overhead: driver and executor memory must be tuned for 16GB.
- ⚠️ Micro-batch latency (seconds) is acceptable for this use case.
- 🔁 A Flink version of the spike detector stays in the backlog for comparison.
