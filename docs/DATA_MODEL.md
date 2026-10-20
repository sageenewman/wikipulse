# Data Model

Where the data lives, what each field means, and how to check and query it. For what the source events contain, see [DATA_SOURCE.md](DATA_SOURCE.md); for why the layers exist, see [DESIGN.md](DESIGN.md).

## The flow

```
Wikimedia stream ──make ingest──▶ wiki.raw ──bronze job──▶ lakehouse.bronze.recentchange
                         └─(invalid)──▶ wiki.dlq

recording ──make replay──▶ wiki.replay ──bronze-replay job──▶ lakehouse.bronze_replay.recentchange
                   └─(invalid)──▶ wiki.replay.dlq
```

Live data and replayed data never mix: separate topics ([ADR-0008](adr/0008-replay-topics.md)) and separate tables ([ADR-0011](adr/0011-spark-bronze-job.md)). Silver and gold are not built yet ([ROADMAP.md](ROADMAP.md)).

## Kafka topics

| Topic | Partitions | Retention | Written by | Contents |
|---|---|---|---|---|
| `wiki.raw` | 3 | 3 days | `make ingest` (the live producer only) | Every valid event |
| `wiki.dlq` | 1 | 14 days | `make ingest` | Events that failed validation |
| `wiki.replay` | 3 | 1 day | `make replay` | Valid events from a recording |
| `wiki.replay.dlq` | 1 | 1 day | `make replay` | Invalid events from a recording |

Every message ([ADR-0007](adr/0007-ingestion-message-contract.md)):

- **Key:** `<wiki>:<title>`, for example `enwiki:Earthquake`; `<wiki>` alone when the event has no title. All changes to one page land in one partition, in order.
- **Value:** the Wikimedia event exactly as received, as UTF-8 JSON.
- **Headers:** `last_event_id`, the event's position in the upstream stream (the producer resumes from it after a restart). Dead letters also carry `error`, the reason validation failed.

Delivery is at least once: a message can appear twice. Deduplication by `meta.id` belongs to silver.

## Iceberg tables

Spark sees the catalog as `lakehouse`. In Lakekeeper the warehouse is `wikipulse` ([ADR-0012](adr/0012-lakekeeper-catalog.md)).

| Table | Source topic | Written by | Partitioned by |
|---|---|---|---|
| `lakehouse.bronze.recentchange` | `wiki.raw` | `bronze` | day of `kafka_timestamp` |
| `lakehouse.bronze_replay.recentchange` | `wiki.replay` | `bronze-replay` | day of `kafka_timestamp` |

### Bronze columns

Bronze holds every message unchanged, so that everything after it can be rebuilt ([ADR-0006](adr/0006-data-scope-and-retention.md)).

| Column | Type | Meaning |
|---|---|---|
| `key` | string | The Kafka key, `<wiki>:<title>` |
| `value` | string | The event's JSON, unparsed |
| `topic` | string | The topic it was read from |
| `kafka_partition` | int | Partition in that topic |
| `kafka_offset` | bigint | Offset in that partition. With `kafka_partition`, identifies the message |
| `kafka_timestamp` | timestamp (UTC) | When the producer wrote it to Kafka. The table is partitioned by its day |
| `headers` | array of (key string, value binary) | The Kafka headers, including `last_event_id` |
| `ingested_at` | timestamp (UTC) | When the bronze batch ran. `ingested_at - kafka_timestamp` is the delay into the lakehouse |

One micro-batch is one Iceberg commit (one snapshot). The job commits every 60 seconds by default, with at most 100,000 messages per batch.

### Where the files are

In the `warehouse` bucket, each table lives under its ID, not its name, so renaming never moves files:

```
s3://warehouse/<table id>/
├── data/kafka_timestamp_day=2026-10-20/*.parquet     the rows
└── metadata/                                          versions, snapshots, manifests
```

The catalog UI (http://localhost:8181/ui) maps names to tables and shows their schema and snapshots. The storage console (http://localhost:9001/rustfs/console/) shows the files.

## Checking the data

- `make check-bronze [JOB=bronze-replay]` compares a table with its topic by partition and offset. It reports `missing` (a hole: lost), `duplicates`, and `not_yet_written` (newer than anything in the table: lag). It is safe to run while the job writes, because the table is read at one pinned snapshot ([ADR-0011](adr/0011-spark-bronze-job.md)).
- `make check-gaps [TOPIC=...]` checks a Kafka topic against Wikimedia's own offsets.

## Querying

`make query SQL="..."` runs one Spark SQL query against the lakehouse and prints up to 100 rows. It accepts reads only (`SELECT`, `WITH`, `SHOW`, `DESCRIBE`, `EXPLAIN`) and refuses anything that writes, so a typo cannot change or drop a table. The lakehouse must be running (`make lakehouse`).

The query passes through `make` and the shell inside double quotes, so:

- use single quotes for strings;
- avoid `$`, which `make` reads as the start of a variable. Until silver exists, fields of the event are read from the JSON with `json_tuple(value, 'field', ...)`, which needs no `$`;
- avoid backticks, which the shell runs as a command.

```bash
# rows, and the time range they cover
make query SQL="SELECT count(*), min(kafka_timestamp), max(kafka_timestamp) FROM lakehouse.bronze.recentchange"

# the busiest wikis
make query SQL="SELECT wiki, count(*) AS events FROM (SELECT json_tuple(value, 'wiki') AS wiki FROM lakehouse.bronze.recentchange) GROUP BY wiki ORDER BY events DESC LIMIT 10"

# bots and humans per event type
make query SQL="SELECT type, count_if(bot = 'true') AS bot, count_if(bot = 'false') AS human FROM (SELECT json_tuple(value, 'type', 'bot') AS (type, bot) FROM lakehouse.bronze.recentchange) GROUP BY type ORDER BY bot + human DESC"

# the latest human edits to English Wikipedia articles
make query SQL="SELECT kafka_timestamp, user, title FROM (SELECT kafka_timestamp, json_tuple(value, 'wiki', 'type', 'bot', 'namespace', 'user', 'title') AS (wiki, type, bot, namespace, user, title) FROM lakehouse.bronze.recentchange) WHERE wiki = 'enwiki' AND type = 'edit' AND bot = 'false' AND namespace = '0' ORDER BY kafka_timestamp DESC LIMIT 10"
```

Iceberg also exposes each table's metadata as tables:

| Query `FROM <table>.<name>` | Shows |
|---|---|
| `snapshots` | One row per commit: time, operation, rows added (`summary['added-records']`) |
| `files` | Each data file: partition, row count, size, path |
| `partitions` | Rows and files per partition |
| `refs` | Branches and tags; `main` is the current snapshot |

```bash
make query SQL="SELECT committed_at, operation, summary['added-records'] FROM lakehouse.bronze.recentchange.snapshots ORDER BY committed_at DESC LIMIT 10"
```
