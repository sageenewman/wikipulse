# ADR-0007: Ingestion message contract

- **Status:** Accepted
- **Date:** 2026-10-04

## Context
The producer writes every Wikimedia event to `wiki.raw`. Consumers (Spark now, others later) depend on how those messages are keyed, partitioned and encoded, so the contract is fixed here before any consumer exists.

## Decision
- **Key:** `<wiki>:<title>`, for example `enwiki:Earthquake`. Falls back to `<wiki>` when an event has no title.
- **Value:** the event JSON exactly as received from Wikimedia, byte for byte. No parsing, renaming or re-serialization.
- **Headers:** `last_event_id` (the upstream stream position of the message). Dead-lettered messages also carry `error` with the reason.
- **Partitions:** `wiki.raw` has 3, `wiki.dlq` has 1.
- **Delivery:** idempotent producer (`enable.idempotence`, which implies `acks=all`), `linger.ms=50`, zstd compression. Overall delivery is at-least-once: duplicates can appear after a reconnect and are removed downstream by `meta.id`.
- **Validation:** an event needs only `meta.id`, `meta.dt`, `type` and `wiki`. Anything else that fails goes to `wiki.dlq`. Wikimedia canary events (`meta.domain = "canary"`) are dropped.
- **Client library:** `confluent-kafka` (librdkafka).

## Alternatives considered
- **Key by `wiki`:** keeps per-wiki order, but Commons alone is about half the stream, so one partition would take half the load.
- **Key by `meta.id` or no key:** spreads load evenly but gives no ordering between related events.
- **Avro value with a registered schema:** smaller and strongly typed, but it means transforming data at ingestion, which ADR-0006 rules out. A schema can be registered for the raw JSON later without changing the messages.
- **One partition:** enough for about 30 events per second, but leaves no room to show parallel consumption.
- **`aiokafka`:** native asyncio, but slower and less widely used than librdkafka.

## Consequences
- ✅ All changes to one page are in one partition, in order.
- ✅ Bronze can store the value untouched, and reprocessing never depends on producer logic.
- ✅ The resume position travels with the data. On startup the producer reads the newest message of each partition and continues from the most recent `last_event_id`, with no state store of its own. Verified live: after a 15-second network cut and after a 40-second shutdown, the raw topic had 0 missing and 0 duplicated events.
- ⚠️ Keys are not unique per message, so topic compaction must stay off.
- ⚠️ Changing the partition count later moves keys to other partitions and breaks ordering across the change.
- ⚠️ In a 45-second live run the three partitions received 580, 567 and 703 messages. The spread is acceptable, but busy pages can skew it and it should be watched.
