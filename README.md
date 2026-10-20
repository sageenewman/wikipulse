# WikiPulse

> 🚧 **Work in progress**

**Real-time breaking-news detection from the live Wikipedia edit stream.**

When something happens in the world, people start editing Wikipedia within minutes. WikiPulse ingests every edit on every Wikipedia in real time, lands the events in an Apache Iceberg lakehouse, and detects abnormal edit-rate spikes that signal real-world events as they unfold.

## Architecture

```
Wikimedia SSE → Python producer → Redpanda (Kafka API)
  → Spark Structured Streaming → Iceberg on S3 (bronze → silver → gold)
  → dbt → Streamlit dashboard
Orchestrated with Airflow · Monitored with Prometheus + Grafana · Deployed with Terraform on AWS
```

## Tech stack

Kafka (Redpanda) · Spark Structured Streaming · Apache Iceberg · dbt · DuckDB · Airflow · Streamlit · Prometheus · Grafana · Terraform · AWS (S3, Glue, Athena) · Docker · GitHub Actions · Python

## Documentation

- [Design document](docs/DESIGN.md)
- [Data source notes](docs/DATA_SOURCE.md)
- [Architecture decisions (ADRs)](docs/adr/)
- [Engineering guidelines](docs/ENGINEERING.md) and [code review guide](docs/CODE_REVIEW.md)
- [Roadmap](docs/ROADMAP.md)
- [Contributing](CONTRIBUTING.md)
- [How AI is used in this repository](CLAUDE.md): the project is built with Claude Code under the owner's direction, and every pull request is examined by a [read-only reviewer agent](.claude/agents/code-reviewer.md) before the owner decides on the merge

## Quickstart

Open the repo in GitHub Codespaces (**Code → Codespaces → Create codespace**). The dev container installs the tooling. Then:

```bash
make up      # start Redpanda and Redpanda Console, create the topics
make ingest  # stream live Wikimedia events into the wiki.raw topic (Ctrl+C to stop)
make check-gaps  # verify that no events were lost or duplicated

# record the last 10 minutes of the stream, then replay them 10x faster
# a replay goes to its own topic, wiki.replay, and never into wiki.raw
make record OUT=data/recordings/sample.jsonl.gz ARGS="--since-minutes 10"
make replay FILE=data/recordings/sample.jsonl.gz SPEED=10
make check-gaps TOPIC=wiki.replay  # verify the replayed copy

# record a past window (Wikimedia keeps about 7 days)
make record OUT=data/recordings/event.jsonl.gz ARGS="--from 2026-09-30T09:00:00Z --to 2026-10-01T00:00:00Z"

# the lakehouse: object storage (RustFS) and the Iceberg catalog (Lakekeeper on Postgres)
make lakehouse        # start them, create the bucket and the catalog's warehouse
make check-lakehouse  # create a test table and check its files reach storage
# catalog web UI: http://localhost:8181/ui
# storage web console: http://localhost:9001/rustfs/console/

# bronze: Spark copies every message of a topic into an Iceberg table
make bronze                          # wiki.raw into lakehouse.bronze.recentchange
make bronze JOB=bronze-replay        # wiki.replay into lakehouse.bronze_replay.recentchange
make check-bronze JOB=bronze-replay  # compare the table with its topic: missing or duplicated messages
# Spark UI: http://localhost:4040 (live job), http://localhost:4041 (replay job)

make test        # run the tests
make test-spark  # run the tests that need Spark, inside the Spark image
make down    # stop everything
```

Redpanda Console is served on port 8080: open **Topics → wiki.raw** to watch events arrive. Run `make help` for all commands.

The rest of the pipeline is still being built. See the [roadmap](docs/ROADMAP.md).
