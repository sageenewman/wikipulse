# ADR-0006: Keep everything at ingestion, filter in processing, tiered retention

- **Status:** Accepted
- **Date:** 2026-10-04

## Context
Only about 9% of the stream is the signal we detect on (human edits to Wikipedia articles), and the pipeline will run continuously on a single VM with a 200GB disk. See [DATA_SOURCE.md](../DATA_SOURCE.md). We had to decide where to filter, which wikis to process, and how long to keep each layer.

## Decision
1. **No filtering at ingestion.** The producer forwards every valid event. Bronze holds the full raw stream.
2. **Filtering happens in processing.** Silver and detection use a configurable allowlist of wikis (`WIKI_ALLOWLIST`), starting with `enwiki` only.
3. **Tiered retention:** Redpanda 3 days, bronze 14 days, silver 90 days, gold unlimited.
4. **Disk usage per layer is monitored**, and the retention values are revisited based on real numbers.

**Amendment, 2026-10-04:** the dead-letter topic `wiki.dlq` is kept for 14 days instead of 3. Dead-lettered events are what we inspect when something breaks, and problems are often noticed days later. The volume is negligible. Once the DLQ triage agent reads the topic daily, this drops to 7 days.

## Alternatives considered
- **Filter in the producer:** about 10x less storage, but dropped data cannot be recovered. A wrong filter, or a new question about bots or Commons, would need data we no longer have.
- **Keep everything forever:** simplest, but at roughly 0.5GB/day compressed (an estimate) the disk fills within a year, and nothing uses raw events that old.
- **All Wikipedias from day one:** more coverage, but thresholds are much harder to tune across wikis with very different volumes.

## Consequences
- ✅ Filters can change and bronze can be reprocessed without data loss, inside the 14-day window.
- ✅ Tuning starts on one high-volume wiki. Adding a language is a config change.
- ⚠️ Baselines can only look back as far as silver and gold do.
- ⚠️ Retention needs scheduled jobs (topic retention settings, Iceberg snapshot expiry and partition deletes) and a disk-usage metric.
- ⚠️ The 0.5GB/day figure is an estimate from a 60-second sample. Measure it on a 24-hour recording.
