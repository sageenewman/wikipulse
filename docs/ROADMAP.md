# Roadmap

Status: `[ ]` todo · `[~]` in progress · `[x]` done · `[-]` dropped (say why)

**Current phase:** Phase 0: Foundations
**MVP:** end of Phase 3.

---

## Phase 0: Foundations
Goal: a repo that opens in Codespaces with one click and has green CI.

- [x] Design document and initial ADRs
- [x] Public GitHub repo
- [ ] License
- [ ] `.devcontainer/devcontainer.json`: Python 3.12, Docker-in-Docker, Java 17 (for Spark), 4-core machine
- [ ] `pyproject.toml` with ruff, mypy, pytest config (uv for dependency management)
- [ ] `Makefile` with `up`, `down`, `test`, `lint`, `fmt`
- [ ] `docker-compose.yml` skeleton with profiles and memory limits
- [ ] `.env.example`
- [ ] GitHub Actions CI: lint + type-check + tests
- [ ] Verify the environment end to end in Codespaces

## Phase 1: Ingestion
Goal: Wikipedia events flowing into Redpanda reliably.

- [ ] Redpanda + Redpanda Console in docker-compose
- [ ] Topics: `wiki.raw`, `wiki.dlq` (document partitions and retention)
- [ ] Async SSE client with a proper User-Agent
- [ ] Reconnect with exponential backoff + resume via `Last-Event-ID`
- [ ] Kafka producer: keying strategy, acks, idempotence, batching (document the choices)
- [ ] Validation: invalid events go to the DLQ, never crash the producer
- [ ] Schema Registry: register the event schema (Avro or JSON Schema, decided in an ADR)
- [ ] Recorder: save N minutes of live events to `data/samples/*.jsonl`
- [ ] Replay mode: produce from a sample file (with optional speed-up)
- [ ] Prometheus metrics: events/sec, reconnects, DLQ count
- [ ] Unit tests (parsing, validation) + integration test with Testcontainers
- [ ] Graceful shutdown (flush the producer on SIGTERM)

## Phase 2: Lakehouse (bronze & silver)
Goal: events land in Iceberg, clean and deduplicated.

- [ ] MinIO (S3-compatible) + Iceberg REST catalog in docker-compose
- [ ] Spark Structured Streaming job: `wiki.raw` → `bronze.recentchange` (append, raw)
- [ ] Checkpointing, verified by killing and restarting the job
- [ ] Silver job: parse, normalize, dedupe on `meta.id` with a watermark
- [ ] Partitioning strategy for silver (documented)
- [ ] Query Iceberg from DuckDB to verify the data
- [ ] Tests for transformation functions

## Phase 3: Real-time detection + dashboard (MVP)
Goal: the system detects breaking news live and shows it on a dashboard.

- [ ] Windowed aggregations: edits per page per 5 minutes (event time + watermark)
- [ ] Spike scoring v1: z-score vs. a rolling baseline per page
- [ ] Noise filters: bots, Wikidata, tiny edits (measure the impact of each)
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

## Phase 5: Observability
- [ ] Prometheus + Grafana in compose
- [ ] Dashboards: consumer lag, throughput, end-to-end latency, DLQ rate, Spark batch duration
- [ ] Alert rules (lag too high, producer disconnected)

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
