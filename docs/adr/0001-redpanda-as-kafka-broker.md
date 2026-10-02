# ADR-0001: Redpanda as the Kafka-compatible broker

- **Status:** Accepted
- **Date:** 2026-10-02

## Context
We need a durable, partitioned event log between ingestion and processing. The whole stack must fit in a 16GB development machine. The Kafka protocol is the de facto standard, and we want to stay compatible with it.

## Decision
Use **Redpanda** in development and on the self-hosted VM. All clients use the standard Kafka protocol and libraries.

## Alternatives considered
- **Apache Kafka (KRaft):** the reference implementation, but a JVM with higher memory use. No built-in Schema Registry or UI.
- **Pulsar:** powerful, but heavier, with a different protocol and a smaller ecosystem.
- **Managed (MSK / Confluent Cloud):** MSK is far too expensive for this project, and Confluent depends on free credits that run out.

## Consequences
- ✅ Single binary, roughly 1/3 the memory of Kafka. Schema Registry and Console are built in.
- ✅ Code is plain Kafka client code, so we can swap to Kafka, MSK or Confluent without code changes.
- ⚠️ We must be careful not to depend on Redpanda-only features.
