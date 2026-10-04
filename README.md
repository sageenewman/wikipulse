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
- [Roadmap](docs/ROADMAP.md)
- [Contributing](CONTRIBUTING.md)

## Quickstart

Open the repo in GitHub Codespaces (**Code → Codespaces → Create codespace**). The dev container installs the tooling. Then:

```bash
make up     # start Redpanda and Redpanda Console
make ps     # check that services are healthy
make down   # stop everything
```

Redpanda Console is served on port 8080. Run `make help` for all commands.

The pipeline itself is still being built. See the [roadmap](docs/ROADMAP.md).
