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
- [x] Topics: `wiki.raw` (3 partitions, 3-day retention), `wiki.dlq` (1 partition, 14-day retention)
- [x] Async SSE client with a proper User-Agent
- [x] Reconnect with exponential backoff, resuming via `Last-Event-ID` held in memory
- [x] Resume after a process restart, from the `last_event_id` header of the last message in Kafka
- [x] Test reconnect behaviour: unit tests with a fake transport, and a live test with the connection cut
- [x] `make check-gaps`: detect lost and duplicated events from the upstream offsets
- [x] Kafka producer: keying, idempotence, batching ([ADR-0007](adr/0007-ingestion-message-contract.md))
- [x] Validation: invalid events go to the DLQ, never crash the producer
- [ ] Run the producer as a container in docker-compose
- [ ] Schema Registry: register a JSON Schema for the raw events (messages stay raw JSON)
- [x] Recorder: save the stream to a file, live or from a point in the past (`make record`)
- [x] Replay mode: publish a recording to Kafka at the original pace, faster, or unpaced (`make replay`)
- [x] Record a past time window (`--from`, `--to`), with upstream topics merged by event time
- [x] Sample of deliberately broken events for exercising the dead-letter path
- [x] First real-event recording: the Flydubai Flight 1073 day, 2026-09-30 (2.66M events)
- [ ] Durable storage for large recordings (they are too big for git)
- [ ] Record 24 hours and re-measure the numbers in [DATA_SOURCE.md](DATA_SOURCE.md)
- [ ] Load test with a recording of an hour or more (the first measurement lasted about a second)
- [ ] Prometheus metrics: events/sec, reconnects, DLQ count
- [x] Unit tests (validation, keying, routing)
- [ ] Integration test with Testcontainers
- [x] Graceful shutdown (flush the producer on SIGINT/SIGTERM)

## Quality pass (before Phase 2)
Goal: the code meets [ENGINEERING.md](ENGINEERING.md), and the checks run by themselves.

- [x] Engineering guidelines ([ENGINEERING.md](ENGINEERING.md))
- [x] Code review guide ([CODE_REVIEW.md](CODE_REVIEW.md))
- [ ] GitHub Actions CI on every PR: lint, type-check, tests
- [ ] Complexity and function-length limits in `ruff`
- [ ] Test coverage measured, with a minimum of 85% in CI
- [ ] `MessageSink` protocol for the Kafka publisher; remove `cast` from the tests
- [ ] Move message routing out of `main.py` into its own module, with injected dependencies
- [ ] Tests for the main loop and for graceful shutdown
- [ ] Split the recorder: stop policy, part writing and merging
- [ ] Integration tests against a real broker for `resume.py` and `check_gaps.py`
- [ ] Decide what happens when a delivery to Kafka fails for good (today it is only counted and logged)
- [ ] Automated reviewer that applies [CODE_REVIEW.md](CODE_REVIEW.md) to every PR

## Phase 2: Lakehouse (bronze & silver)
Goal: events land in Iceberg, clean and deduplicated.

- [ ] MinIO (S3-compatible) + Iceberg REST catalog in docker-compose
- [ ] Spark Structured Streaming job: `wiki.raw` → `bronze.recentchange` (append, raw)
- [ ] Checkpointing, verified by killing and restarting the job
- [ ] Silver job: parse, normalize, dedupe on `meta.id` with a watermark
- [ ] Wiki allowlist (`WIKI_ALLOWLIST`, starting with `enwiki`) applied in silver, never at ingestion
- [ ] Partitioning strategy for silver (documented)
- [ ] Query Iceberg from DuckDB to verify the data
- [ ] Export a time window from bronze to a recording file
- [ ] Tests for transformation functions

## Phase 3: Real-time detection + dashboard (MVP)
Goal: the system detects breaking news live and shows it on a dashboard.

- [ ] Redesign the detection rule against the Flydubai recording: window length, thresholds, distinct editors, pages with no history (finding 16 in [DATA_SOURCE.md](DATA_SOURCE.md))
- [ ] Windowed aggregations: edits and distinct editors per page (event time + watermark)
- [ ] Spike scoring v1: z-score vs. a rolling baseline per page
- [ ] Synthetic spike generator: inject a burst of edits into a quiet recording, for tests with a known answer
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

### DLQ triage agent
Goal: nobody has to read the dead-letter topic by hand. An agent reads it, decides whether a failure is a bug on our side, and opens a ticket.

Needs first: the pipeline running continuously, replay mode (to inject broken events for testing), and an LLM API key.

- [ ] Scheduled job, once a day by default, with a configurable interval (shorter for testing)
- [ ] Read only the dead-letter records that arrived since the last run
- [ ] Group records by failure reason and event shape, so many records of one failure become one finding
- [ ] LLM analysis per group: our bug, upstream data problem, or transient
- [ ] For our bugs: open a GitHub issue in this repo with evidence, sample records, the suspect code and a suggested fix
- [ ] Do not open a second issue for a failure that already has an open one
- [ ] Guardrails: record contents are untrusted text, the agent can only open issues from a fixed template, and there is a daily cap on issues
- [ ] Once the agent is running, reduce `wiki.dlq` retention from 14 days to 7

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
