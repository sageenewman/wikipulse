# ADR-0011: The bronze job: Spark in a container, raw rows, one table per source

- **Status:** Accepted
- **Date:** 2026-10-20

## Context
Phase 2 starts writing the stream into the lakehouse. The first job copies every message of `wiki.raw` into an Iceberg table, `bronze.recentchange`. Bronze is the layer everything else can be rebuilt from ([ADR-0006](0006-data-scope-and-retention.md)), so it must not lose, duplicate or alter messages.

The roadmap had planned to install Java and Spark in the dev container and to move to a 4-core machine for Spark.

## Decision
- **Spark runs in its own container**, built from the official `apache/spark:4.1.3-python3` image (`streaming/Dockerfile`), under the compose profile `streaming`. The jobs run on it in the codespace, and CI builds it and runs the Spark tests in it (a `test` stage of the same Dockerfile). The plan is for a server to run the same image. The Kafka source and Iceberg connectors are resolved when the image is built, so a job starts without downloading anything. Spark runs in local mode with a 1GB heap and a 2GB container limit.
- **Versions: Spark 4.1.3 with Iceberg 1.12.0.** Spark 4.2 is newer, but Iceberg has no runtime for it yet. The local catalog server was Iceberg 1.10.1, and is Lakekeeper since [ADR-0012](0012-lakekeeper-catalog.md); client and server talk through the REST protocol, which is stable across versions.
- **Bronze rows are the Kafka messages as they arrived:** key and value as text (the producer writes UTF-8 JSON, [ADR-0007](0007-ingestion-message-contract.md)), topic, partition, offset, Kafka timestamp, headers, and the time the batch ran. Nothing is parsed or filtered.
- **Partition and offset are kept**, so the table can be checked against its topic: `make check-bronze` reports missing and duplicated messages. It reads the table at one pinned snapshot, taken before the topic is read, and computes every count in one query. So it can run while the job writes: a message newer than anything the table has in its partition is reported as not yet written, while a hole below that point is reported as missing.
- **The tests that need Spark run inside the Spark image** (`make test-spark`, and a CI job). This also checks that `streaming/` runs on the image's Python 3.10.
- **The table is partitioned by day** of the Kafka timestamp: bronze is read by time range and expired by day.
- **One micro-batch per minute by default** (`BRONZE_TRIGGER_SECONDS`), with at most 100,000 messages per batch (`BRONZE_MAX_OFFSETS_PER_TRIGGER`).
- **Each source has its own table.** Live data goes to `lakehouse.bronze.recentchange`, replays to `lakehouse.bronze_replay.recentchange` (the `bronze-replay` service). The settings refuse any topic other than `wiki.raw` for the live table, the same rule as [ADR-0008](0008-replay-topics.md).
- **The checkpoint is on a Docker volume**, at a path derived from the table name, so two jobs can never share one.
- **Python 3.10 for this package.** The Spark image ships Python 3.10, so `streaming/` is checked as 3.10 code by ruff and cannot share modules that use 3.11 features (the JSON log formatter is a small copy).
- **PySpark is not installed in the project environment.** mypy treats it as untyped.

## Alternatives considered
- **Java and PySpark in the dev container:** the original plan. It needs a rebuild of the codespace, Spark would run without a memory limit, and production would run something different. It becomes the better choice when silver has transformation logic that needs fast unit tests against Spark.
- **Parsing the JSON into columns already in bronze:** easier queries, but a parsing bug would damage the only copy of the source. Parsing belongs in silver.
- **The checkpoint in object storage:** needs Hadoop's S3 connector and its settings. It is the right choice in the cloud, where a local volume does not survive the machine.
- **A trigger of a few seconds:** fresher data, but each batch writes at least one file per partition, and many small files slow down reads. A minute is fresh enough for bronze. Detection in Phase 3 sets its own interval.
- **A 4-core machine:** measured first instead. Two bronze jobs ran side by side at about 600MB each, with the whole stack at about 2.5GB of 8GB.
- **A Python 3.12 image with PySpark installed by pip:** the same Python as the rest of the repository, but a hand-built Spark image instead of the one the Spark project maintains.

## Consequences
- ✅ Verified end to end: a replay of 16,945 events and a live run of 3,818 events each arrived in their table with 0 missing and 0 duplicated messages.
- ✅ A day of the stream is about 0.9GB of Parquet (16,945 events took 3.6MB).
- ✅ Replayed data cannot reach the live table: the job refuses to start.
- ⚠️ The image is 2.55GB, almost all of it the official Spark image.
- ⚠️ The checkpoint and the table belong together. Deleting one without the other makes the job skip or repeat messages. `make clean` deletes both.
- ✅ The checker is shown to fail: its tests plant a duplicate and a hole, and breaking the counting logic on purpose made them fail.
- ⚠️ Every CI run downloads the 2.2GB Spark image to run the Spark tests (the first runs took about a minute).
- ⚠️ Without PySpark in the project environment, mypy does not check calls into Spark.
- ⚠️ Restart safety (killing the job and starting it again) is not verified yet; it is the next roadmap item.
