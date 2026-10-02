# ADR-0003: Apache Iceberg as the table format

- **Status:** Accepted
- **Date:** 2026-10-02

## Context
Events land in object storage (MinIO locally, S3 in the cloud). We need ACID writes from streaming, schema evolution, and reads from several engines (Spark, DuckDB, Athena).

## Decision
Use **Apache Iceberg** tables with a REST catalog locally and the AWS Glue Data Catalog in the cloud.

## Alternatives considered
- **Delta Lake:** mature and strong in the Databricks ecosystem, but less engine-neutral, with weaker Athena/DuckDB parity.
- **Plain Parquet:** simple, but no transactions, no schema evolution, and no time travel. Concurrent streaming writes are unsafe.

## Consequences
- ✅ Spark, DuckDB, Athena and Trino can all read the same tables.
- ✅ Snapshots, time travel, hidden partitioning and schema evolution.
- ✅ First-class AWS support (Glue, Athena).
- ⚠️ Streaming creates many small files, so compaction and snapshot expiry must be scheduled (Phase 4).
- ⚠️ Catalog choice matters. A local REST catalog must mirror the Glue setup closely enough.
