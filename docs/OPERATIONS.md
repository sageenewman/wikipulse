# Operations Guide

How to run the system, look at it, and fix it when something goes wrong. Everything here runs in the codespace ([ADR-0004](adr/0004-codespaces-dev-environment.md)); `make help` lists every command.

## The services

The stack is defined in [`docker-compose.yml`](../docker-compose.yml). Every service has a memory limit, and optional services sit behind compose profiles, so only what is needed runs.

| Service | Profile | Purpose | Port / UI | Memory limit | Data volume |
|---|---|---|---|---|---|
| `redpanda` | default | Kafka-compatible broker, with Schema Registry | `19092` Kafka from the codespace, `18081` Schema Registry, `9644` admin | 1.5GB | `redpanda-data` |
| `console` | default | Redpanda Console: topics, messages, consumers | http://localhost:8080 | 256MB | — |
| `object-store` | `lakehouse` | RustFS, S3-compatible storage for table files | `9000` S3 API, http://localhost:9001/rustfs/console/ | 512MB | `object-store-data` |
| `catalog-db` | `lakehouse` | Postgres, the catalog's database | — | 256MB | `catalog-db` |
| `catalog-migrate` | `lakehouse` | Creates or upgrades the catalog's database tables, then exits | — | 256MB | — |
| `lakekeeper` | `lakehouse` | The Iceberg REST catalog, with a web UI | http://localhost:8181/ui | 512MB | — |
| `bronze` | `streaming` | Spark job: `wiki.raw` into `lakehouse.bronze.recentchange` | http://localhost:4040 (Spark UI) | 2GB | `spark-checkpoints` |
| `bronze-replay` | `streaming` | Spark job: `wiki.replay` into `lakehouse.bronze_replay.recentchange` | http://localhost:4041 (Spark UI) | 2GB | `spark-checkpoints` |

The ingestion producer (`make ingest`, `make record`, `make replay`) runs as a Python process in the codespace, not as a container (roadmap item).

**Opening a UI.** The ports are forwarded by the codespace: open them from the *Ports* tab in VS Code, or from your own machine with `gh codespace ports forward <port>:<port> -c <codespace name>` and then `http://localhost:<port>`. The storage console logs in with `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY` (defaults in [`.env.example`](../.env.example)). A Spark UI exists only while its job runs.

## Starting and stopping

| Command | What it does |
|---|---|
| `make up` | Starts Redpanda and the Console, and creates the topics |
| `make lakehouse` | Starts storage, Postgres and the catalog, then creates the bucket (`make buckets`) and bootstraps the catalog and its warehouse (`make warehouse`). Safe to run again |
| `make bronze` / `make bronze JOB=bronze-replay` | Starts the lakehouse if needed, builds the Spark image, and starts a bronze job |
| `make ingest` | Streams live Wikimedia events into `wiki.raw` until Ctrl+C. After a restart it continues from the last position stored in Kafka |
| `make ps` / `make logs` | Status of the services / follow their logs |
| `make down` | Stops everything. Data is kept |
| `make clean` | Stops everything and **deletes all data**: Kafka topics, tables, catalog and Spark checkpoints |

**When to use `make clean`.** Tables, the catalog database and the Spark checkpoints belong together. Deleting one without the others makes a job skip or repeat messages, so they are only ever deleted together, which `make clean` does. It is needed after changing the storage key or the catalog's encryption key, and when switching the catalog.

**The codespace stops by itself** after about 30 minutes without activity, and every container stops with it (`Exited (255)` in `docker ps -a`). Nothing is lost: run the same `make` targets again. The bronze jobs continue from their checkpoints. Stop the codespace when you finish (`gh codespace stop -c <name>`); its free hours are limited.

## Common tasks

**Bring live data into the lakehouse**
```bash
make up && make bronze   # Kafka, the lakehouse, and the live bronze job
make ingest              # in a second terminal; Ctrl+C to stop
make check-bronze        # the table against the topic
```

**Test with recorded data instead of the live stream**
```bash
make record OUT=data/recordings/test.jsonl.gz ARGS="--since-minutes 10"
make replay FILE=data/recordings/test.jsonl.gz SPEED=0   # unpaced; into wiki.replay
make bronze JOB=bronze-replay
make check-bronze JOB=bronze-replay
```
Replays never reach the live topics or the live table ([ADR-0008](adr/0008-replay-topics.md)). A bronze job writes a batch every 60 seconds by default; `BRONZE_TRIGGER_SECONDS=10 make bronze` is faster for tests.

**Check that nothing was lost or duplicated**

| Command | Compares | Notes |
|---|---|---|
| `make check-gaps [TOPIC=...]` | Messages in a topic against Wikimedia's own offsets | Ingestion: did the producer lose or repeat events? |
| `make check-bronze [JOB=...]` | A bronze table against its topic | Safe while the job runs. `not_yet_written` is lag, not an error; `missing` and `duplicates` must be 0 |
| `make check-lakehouse` | Storage and catalog end to end | Creates and drops a test table |

**Look at the data:** `make query SQL="..."`, see [DATA_MODEL.md](DATA_MODEL.md#querying).

**Run the tests:** `make test` (regular), `make test-spark` (inside the Spark image).

## Troubleshooting

| Symptom | Cause | What to do |
|---|---|---|
| Every container shows `Exited (255)` | The codespace stopped while idle | Start what you need again (`make up`, `make bronze`) |
| A bronze job exited with `CommitStateUnknownException` | The catalog did not answer a commit, so Iceberg cannot tell whether it landed and stops rather than risk duplicates | Look at `docker compose --profile lakehouse logs lakekeeper`. Start the job again with `make bronze`: it redoes the batch, and a batch that already landed is skipped. Confirm with `make check-bronze` |
| `make check-bronze` reports `missing` or `duplicates` | Messages were really lost or written twice | Keep the job stopped and investigate before writing more: compare `kafka_partition`/`kafka_offset` ranges in the table ([DATA_MODEL.md](DATA_MODEL.md)) |
| `make check-bronze` reports `not_yet_written` | The job is behind the topic | Wait for the next batches; check the Spark UI |
| A bronze job refuses to start: `only wiki.raw may be written to lakehouse.bronze.recentchange` | A replay or test topic was configured for the live table | Use `JOB=bronze-replay`, or set a different `BRONZE_TABLE` |
| A bronze job fails because offsets are no longer available | The job was stopped longer than the topic keeps messages (`wiki.raw`: 3 days), so they were deleted before it read them | Those messages are gone from Kafka. Decide whether to accept the gap or re-ingest from a recording |
| Every table read or write fails with HTTP 403 | The storage key or `CATALOG_ENCRYPTION_KEY` changed after the warehouse was created; the catalog still uses the old key | `make clean`, then start again |
| `make check-lakehouse` or `make warehouse` fails | A lakehouse service is not healthy | `make ps`, then `docker compose --profile lakehouse logs <service>` |
| `make lakehouse` fails on `catalog-migrate` | The catalog database could not be migrated | `docker compose --profile lakehouse logs catalog-migrate catalog-db` |
| The producer starts far behind live after a restart | It resumes from the last position stored in Kafka and catches up | Expected. Set `RESUME_ON_START=false` to start from the live edge |
| A replay refuses to start: replay topics must differ from the live topics | `REPLAY_RAW_TOPIC` or `REPLAY_DLQ_TOPIC` names a live topic | Fix the variable; see ADR-0008 |
| An S3 request from the codespace with `curl` returns 400 `missing header: x-amz-content-sha256` | The codespace's `curl` 7.88 does not sign S3 requests completely | Run it inside the `object-store` container, as the scripts do |

## Configuration

Settings come from environment variables; [`.env.example`](../.env.example) lists them with their defaults, and `.env` (not in git) overrides them. Ingestion reads its settings in [`ingestion/config.py`](../ingestion/config.py), the streaming jobs in [`streaming/config.py`](../streaming/config.py), and the services in [`docker-compose.yml`](../docker-compose.yml).
