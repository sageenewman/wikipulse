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
make record OUT=data/recordings/sample.jsonl.gz ARGS="--since-minutes 10"
make replay FILE=data/recordings/sample.jsonl.gz SPEED=10

# record a past window (Wikimedia keeps about 7 days)
make record OUT=data/recordings/event.jsonl.gz ARGS="--from 2026-09-30T09:00:00Z --to 2026-10-01T00:00:00Z"
make test    # run the tests
make down    # stop everything
```

Redpanda Console is served on port 8080: open **Topics → wiki.raw** to watch events arrive. Run `make help` for all commands.

The rest of the pipeline is still being built. See the [roadmap](docs/ROADMAP.md).
