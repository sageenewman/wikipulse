# WikiPulse: Design Document

**Status:** draft · **Owner:** Sagee Newman · **Last updated:** 2026-10-02

## 1. Summary

When something happens in the world (an earthquake, a celebrity death, an election upset), people start editing the related Wikipedia article within minutes. Wikimedia publishes **every edit on every wiki in real time** as a public event stream: tens of events per second, millions per day.

**WikiPulse** ingests that stream, lands it in an Iceberg lakehouse, and detects **abnormal spikes in edit activity** to surface breaking news as it happens. It also provides historical analytics and a live dashboard.

## 2. Goals

### Product goals
1. **Breaking news detection:** find pages with sudden edit-rate spikes, minutes after a real-world event.
2. **Edit wars:** find pages where different editors keep reverting each other.
3. **Who edits:** bots vs. humans, by language and time of day.
4. **Hebrew Wikipedia lens:** compare Hebrew Wikipedia activity with other languages.

### Engineering goals
- An end-to-end streaming lakehouse built on the industry-standard stack.
- Reliable: survives disconnects and restarts without losing or duplicating data.
- Reproducible: anyone can run it with one command in Codespaces.
- Observable: throughput, lag and latency are measured, not guessed.
- Tested: deterministic tests through recorded-event replay.

### Non-goals
- Sub-second latency (seconds to minutes is fine for news detection).
- Production-grade multi-tenant infrastructure.
- ML-heavy anomaly detection (start with statistics, improve only if needed).

## 3. Architecture

```
 Wikimedia EventStreams (SSE)
            │
            ▼
 ┌─────────────────────┐   recorder → file    ┌──────────────┐
 │ Producer (Python)   │────────────────────▶│ Replay mode  │  (tests, demos, backfill)
 └─────────┬───────────┘                     └──────────────┘
           ▼
 ┌─────────────────────┐
 │ Redpanda (Kafka API)│  topics: wiki.raw / wiki.alerts / wiki.dlq
 │ + Schema Registry   │
 └─────────┬───────────┘
           ▼
 ┌──────────────────────────────┐
 │ Spark Structured Streaming   │  clean, dedupe, window, detect spikes
 └─────────┬────────────────────┘
           ▼
 ┌──────────────────────────────┐
 │ Iceberg Lakehouse (S3/MinIO) │  bronze → silver → gold
 └─────────┬────────────────────┘
           ▼
 ┌──────────────┐     ┌────────────────────┐
 │ dbt + DuckDB │────▶│ Streamlit dashboard│
 └──────────────┘     └────────────────────┘

 Airflow:              dbt runs, Iceberg maintenance, backfills
 Prometheus + Grafana: lag, events/sec, latency, DLQ
 Terraform:            AWS S3 + Glue + Athena
 GitHub Actions:       lint, type-check, tests, build
```

### Data layers (medallion)

| Layer | Contents | Written by |
|---|---|---|
| **Bronze** | Raw events exactly as received. Lets us always reprocess from scratch. | Spark streaming |
| **Silver** | Parsed, normalized, deduplicated events with a stable schema | Spark streaming |
| **Gold** | Analytical tables: trends, edit wars, daily stats, spikes | dbt + Spark |

### Topics

| Topic | Purpose |
|---|---|
| `wiki.raw` | Raw events from the producer |
| `wiki.alerts` | Detected spikes |
| `wiki.dlq` | Events that failed validation |

## 4. Stack and rationale

Detailed reasoning lives in [ADRs](adr/).

| Component | Choice | Alternatives | Why |
|---|---|---|---|
| Broker | **Redpanda** | Kafka, Pulsar | Kafka API, single binary, about 1/3 the memory, built-in Schema Registry. Swappable for MSK/Confluent. [ADR-0001](adr/0001-redpanda-as-kafka-broker.md) |
| Stream processing | **Spark Structured Streaming** | Flink, Kafka Streams | One engine for streaming, batch backfills and table maintenance, with native Iceberg support and a large ecosystem. Latency needs are seconds, not milliseconds. [ADR-0002](adr/0002-spark-structured-streaming.md) |
| Table format | **Apache Iceberg** | Delta Lake, raw Parquet | Engine-neutral (Spark, DuckDB, Athena, Trino), ACID, time travel, schema evolution, native AWS support. [ADR-0003](adr/0003-iceberg-table-format.md) |
| Transformations | **dbt** + DuckDB | Hand-written SQL | Industry standard. Tests and docs built in. The same models run on Athena in the cloud. |
| Orchestration | **Airflow** | Dagster, Prefect | The most widely adopted orchestrator. Runs in a lightweight standalone mode. |
| Dashboard | **Streamlit** + **Grafana** | Superset, Metabase | Streamlit is pure Python and fast to build. Grafana is the ops standard. |
| Monitoring | **Prometheus + Grafana** | Datadog | Free and the industry standard. |
| Dev environment | **GitHub Codespaces** | Local | The full stack needs about 16GB. One-click, reproducible setup for every contributor. [ADR-0004](adr/0004-codespaces-dev-environment.md) |
| Cloud | **S3 + Glue + Athena** via Terraform, compute on **Oracle Always Free** | MSK, EMR | Near-zero cost: pay-per-use services only. [ADR-0005](adr/0005-cloud-cost-strategy.md) |
| CI | **GitHub Actions** | Jenkins | Built in and free. |
| Language | **Python 3.12** | Java | The lingua franca of data engineering. A Java producer is a possible later addition. |

## 5. Key design concerns

| # | Challenge | Why it's hard | Approach |
|---|---|---|---|
| 1 | **Disconnects & duplicates** | SSE connections drop. Reconnecting can lose or repeat events. | Persist `Last-Event-ID` and resume from it. At-least-once delivery, deduplicated in silver by `meta.id`. |
| 2 | **Late / out-of-order events** | Processing-time windows give wrong answers. | Event-time windows with watermarks. |
| 3 | **Small files** | Streaming micro-batches create many tiny Iceberg files and reads slow down. | Tune the trigger interval. Scheduled compaction + snapshot expiry in Airflow. |
| 4 | **Schema evolution** | Event types have different fields, and Wikimedia schemas change. | Schema Registry compatibility rules, Iceberg schema evolution, DLQ for invalid events. |
| 5 | **Bot noise** | Bots, mostly on Wikidata, dominate volume and mask human activity. | Keep everything in bronze. Filter and segment in silver and gold. Measure the impact. |
| 6 | **Defining a spike** | Some pages are always busy, and new pages have no baseline. | v1: z-score vs. a rolling baseline with a minimum-activity threshold. Validate against known events. |
| 7 | **Resource limits** | Redpanda + Spark + Airflow + MinIO is tight on 16GB. | Compose profiles and per-container memory limits. |
| 8 | **Testing streaming code** | You can't assert against a live stream. | Record real events to files and replay them deterministically. Pure functions get unit tests, and Testcontainers covers integration. |
| 9 | **Cloud cost** | One forgotten service can be expensive. | Budget alerts, no MSK/EMR/NAT, `terraform destroy` after demos. |
| 10 | **Codespaces quota** | About 30 hours/month on a 4-core machine. | Auto-stop, and move 24/7 runtime to Oracle early. |
| 11 | **Scope creep** | The biggest risk to finishing. | Strict MVP (Phase 3). Ideas go to the backlog. |
| 12 | **Integration complexity** | Many components have to work together. | Add one component per phase. Every phase ends with a working system. |

## 6. Spike detection v1

For each `(wiki, page_title)` and each 5-minute event-time window:

```
score = (edits_in_window - rolling_mean) / max(rolling_std, floor)
alert if score > threshold AND edits_in_window >= min_edits AND distinct_editors >= min_editors
```

- Exclude bot edits by default.
- Requiring a minimum number of distinct editors filters out a single user making many small edits.
- Start from defaults (threshold 4, min_edits 5, min_editors 3), then tune on replayed data.
- **Success metric:** detection delay (minutes between the real-world event and the alert) for a set of known events.

## 7. Phases

See [ROADMAP.md](ROADMAP.md) for the detailed breakdown.

| Phase | Deliverable | Est. |
|---|---|---|
| 0. Foundations | Repo, Codespaces, CI | 1 wk |
| 1. Ingestion | Reliable producer → Redpanda, replay mode | 1–2 wk |
| 2. Lakehouse | Bronze/silver Iceberg tables | 2 wk |
| 3. Real-time | Spike detection + dashboard → **MVP** | 2 wk |
| 4. Analytics | dbt gold models + Airflow | 2 wk |
| 5. Observability | Prometheus + Grafana | 1 wk |
| 6. Cloud | Terraform AWS + Oracle 24/7 | 2 wk |
| 7. Polish | README, benchmarks | 1 wk |

## 8. Success criteria

- `make up` brings up the full pipeline in Codespaces with no manual steps.
- Kill and restart any component: no data loss, no duplicates in silver.
- Measured and published: events/day, end-to-end latency p50/p99, detection delay.
- At least 3 real-world events detected and documented in the README.
- CI is green, and test coverage includes parsing, dedup and spike scoring.

## 9. Open questions

- Avro or JSON Schema for the Schema Registry?
- Which Iceberg REST catalog to use locally (Lakekeeper, Nessie, or the reference implementation)?
- Silver partitioning: by `day` only, or by `day` + `wiki`?
- Streamlit reads from Iceberg via DuckDB, or from a small serving table?
