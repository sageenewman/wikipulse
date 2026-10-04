# Roadmap

Status: `[ ]` todo · `[~]` in progress · `[x]` done · `[-]` dropped (say why)

**Current phase:** Phase 1: Ingestion
**MVP:** end of Phase 3.

---

## Phase 0: Foundations
Goal: a repo that opens in Codespaces with one click and has green CI.

- [x] Design document and initial ADRs
- [x] Public GitHub repo
- [ ] License
- [x] `.devcontainer/devcontainer.json`: Docker-in-Docker, uv-managed Python 3.12, 2-core machine (Java 17 and 4 cores are added with Spark in Phase 2)
- [x] `pyproject.toml` with ruff, mypy, pytest config (uv for dependency management)
- [x] `Makefile` with `up`, `down`, `test`, `lint`, `fmt`
- [x] `docker-compose.yml` with Redpanda, Redpanda Console and memory limits
- [x] `.env.example`
- [x] Verify the environment end to end in Codespaces
- [ ] GitHub Actions CI: lint + type-check + tests (once there is code to check)

## Phase 1: Ingestion
Goal: Wikipedia events flowing into Redpanda reliably.

- [x] Redpanda + Redpanda Console in docker-compose
- [x] Topics: `wiki.raw` (3 partitions), `wiki.dlq` (1 partition), 3-day retention
- [x] Async SSE client with a proper User-Agent
- [x] Reconnect with exponential backoff, resuming via `Last-Event-ID` held in memory
- [ ] Resume after a process restart, from the `last_event_id` header of the last message in Kafka
- [ ] Test reconnect behaviour (drop the connection, check for gaps and duplicates)
- [x] Kafka producer: keying, idempotence, batching ([ADR-0007](adr/0007-ingestion-message-contract.md))
- [x] Validation: invalid events go to the DLQ, never crash the producer
- [ ] Run the producer as a container in docker-compose
- [ ] Schema Registry: register a JSON Schema for the raw events (messages stay raw JSON)
- [ ] Recorder: save N minutes of live events to `data/samples/*.jsonl`
- [ ] Record 24 hours and re-measure the numbers in [DATA_SOURCE.md](DATA_SOURCE.md)
- [ ] Replay mode: produce from a sample file (with optional speed-up)
- [ ] Prometheus metrics: events/sec, reconnects, DLQ count
- [x] Unit tests (validation, keying, routing)
- [ ] Integration test with Testcontainers
- [x] Graceful shutdown (flush the producer on SIGINT/SIGTERM)

## Phase 2: Lakehouse (bronze & silver)
Goal: events land in Iceberg, clean and deduplicated.

- [ ] MinIO (S3-compatible) + Iceberg REST catalog in docker-compose
- [ ] Spark Structured Streaming job: `wiki.raw` → `bronze.recentchange` (append, raw)
- [ ] Checkpointing, verified by killing and restarting the job
- [ ] Silver job: parse, normalize, dedupe on `meta.id` with a watermark
- [ ] Wiki allowlist (`WIKI_ALLOWLIST`, starting with `enwiki`) applied in silver, never at ingestion
- [ ] Partitioning strategy for silver (documented)
- [ ] Query Iceberg from DuckDB to verify the data
- [ ] Tests for transformation functions

## Phase 3: Real-time detection + dashboard (MVP)
Goal: the system detects breaking news live and shows it on a dashboard.

- [ ] Windowed aggregations: edits per page per 5 minutes (event time + watermark)
- [ ] Spike scoring v1: z-score vs. a rolling baseline per page
- [ ] Signal filter: `type in (edit, new)`, `namespace = 0`, non-bot, Wikipedia projects only (see [DATA_SOURCE.md](DATA_SOURCE.md))
- [ ] Tune window size and thresholds on recorded data (the signal is only ~3 events/sec)
- [ ] Emit spikes to the `wiki.alerts` topic + an Iceberg table
- [ ] Streamlit dashboard: live trending, events/sec, bot vs. human, Hebrew Wikipedia view
- [ ] Validate against real events: detection delay in minutes

## Phase 4: Analytics & orchestration
- [ ] dbt project (dbt-duckdb) reading silver Iceberg tables
- [ ] Gold models: daily stats per wiki, top pages, edit wars, bot share
- [ ] dbt tests (not_null, unique, accepted_values, freshness) + docs site
- [ ] Airflow (standalone, low memory) in compose
- [ ] DAG: hourly dbt build
- [ ] DAG: Iceberg maintenance (compaction, expire snapshots, remove orphan files)
- [ ] DAG: backfill from bronze
- [ ] DAG: retention (bronze 14 days, silver 90 days), see [ADR-0006](adr/0006-data-scope-and-retention.md)

## Phase 5: Observability
- [ ] Prometheus + Grafana in compose
- [ ] Dashboards: consumer lag, throughput, end-to-end latency, DLQ rate, Spark batch duration
- [ ] Disk usage per layer (topics, bronze, silver, gold), used to revisit retention values
- [ ] Alert rules (lag too high, producer disconnected, disk filling up)

## Phase 6: Cloud
- [ ] AWS budget alert before the first `terraform apply`
- [ ] Terraform: S3 bucket, Glue Data Catalog, Athena workgroup, IAM roles
- [ ] Terraform remote state (S3 + locking)
- [ ] Point Iceberg at S3 + Glue, and query from Athena
- [ ] dbt-athena target for the gold models
- [ ] Always-on deployment on a free-tier VM
- [ ] Terraform CI: fmt + validate + plan

## Phase 7: Polish
- [ ] README: architecture diagram, demo GIF, quickstart, design highlights
- [ ] Benchmarks: throughput, end-to-end latency p50/p99, detection delay
- [ ] Review ADRs and the design document

---

## Backlog (after MVP)
- Serving API for alerts and trends
- Producer implementation in Java
- Flink version of the spike detector for comparison
- Hybrid search over edit comments with Elasticsearch
- LLM-generated summary of what is happening per spike
