# Architecture Decision Records

An ADR records one significant decision: the context, what we chose, and the consequences. ADRs are never deleted. If a decision changes, write a new ADR that supersedes the old one.

| # | Decision | Status |
|---|---|---|
| [0001](0001-redpanda-as-kafka-broker.md) | Redpanda as the Kafka-compatible broker | Accepted |
| [0002](0002-spark-structured-streaming.md) | Spark Structured Streaming for stream processing | Accepted |
| [0003](0003-iceberg-table-format.md) | Apache Iceberg as the table format | Accepted |
| [0004](0004-codespaces-dev-environment.md) | GitHub Codespaces as the dev environment | Accepted |
| [0005](0005-cloud-cost-strategy.md) | Near-zero-cost cloud strategy | Accepted |
| [0006](0006-data-scope-and-retention.md) | Keep everything at ingestion, filter in processing, tiered retention | Accepted |

New ADRs: copy [template.md](template.md) and use the next number.
