# ADR-0012: Lakekeeper on Postgres as the Iceberg catalog, with remote signing

- **Status:** Accepted. Replaces the catalog part of [ADR-0010](0010-local-lakehouse-storage.md); RustFS stays the object store.
- **Date:** 2026-10-20

## Context
[ADR-0010](0010-local-lakehouse-storage.md) used the Iceberg project's reference REST catalog, which keeps its state in SQLite. SQLite allows one writer at a time and, by default, fails at once when the file is locked.

That happened while the bronze jobs ran ([ADR-0011](0011-spark-bronze-job.md)). A commit coincided with another catalog request, the catalog answered HTTP 500 (`SQLITE_BUSY: database is locked`), and the live job stopped with `CommitStateUnknownException`: Iceberg could not tell whether the commit had landed, so it did not retry. The snapshot history showed it had not landed, and the restarted job redid the batch without duplicates.

Two SQLite settings, `journal_mode=WAL` and `busy_timeout`, made the failure rare in a stress test, but not impossible. Concurrent writers are coming anyway: Iceberg maintenance jobs will write next to the streaming jobs, and an always-on server will run without anyone watching. There is no production yet, so there is no reason to keep a stop-gap.

## Decision
- **Catalog: Lakekeeper** (`quay.io/lakekeeper/catalog:v0.14.1`), an Apache-2.0 Iceberg REST catalog, with its state in **Postgres** (`postgres:17.11-alpine`). Both are pinned by digest.
- **Startup:** `catalog-migrate` creates or upgrades Lakekeeper's tables and exits. `lakekeeper` serves the REST API at `/catalog`, the management API at `/management`, and a web UI at `/ui`.
- **Setup:** `scripts/create-warehouse.sh` (`make warehouse`, part of `make lakehouse`) bootstraps Lakekeeper once and creates the warehouse `wikipulse` on the RustFS bucket. It is safe to run again.
- **Clients hold no storage credentials. Lakekeeper signs each S3 request (remote signing).** It signs only requests inside the location of a table the client loaded. The Spark containers carry no storage keys at all.
- **STS (vended credentials) is off.** Lakekeeper tests STS against AWS, Silo and SeaweedFS, not RustFS.
- **Dropped tables are deleted at once** (`delete-profile: hard`): this is development data, and soft deletion would keep it for days.
- **No authentication or authorization locally** (Lakekeeper's `allowall`). OpenID Connect and an authorizer can be added without changing the clients' catalog settings.

## Alternatives considered
- **Keep the reference catalog with WAL and a busy timeout:** a one-line change, verified by a stress test. It makes lock failures rare, not impossible: a lock held longer than the timeout still stops the job. Rejected in favour of removing the cause while there is no production to protect.
- **The reference catalog on Postgres:** the same catalog with a real database. Its image includes only the SQLite driver, so it would need a custom image, and it would still be a test fixture with no UI and no access control.
- **Nessie on Postgres:** a production catalog, but heavier, and its main feature, branches of tables, is not something the project needs.
- **Vended credentials instead of remote signing:** temporary keys limited to one table, which more clients support (DuckDB does not support remote signing). It needs STS on the storage. It becomes the choice with storage that has tested STS: AWS S3, or Silo or SeaweedFS locally.
- **Clients with their own storage keys** (`client-managed`): the simplest, and what the previous setup did. But then every client can read and write the whole bucket, and the catalog controls nothing.

## Consequences
- ✅ Postgres handles concurrent writers; the lock failure is gone, not rare. The stress test that broke SQLite (two jobs committing every 10 seconds, live ingestion, a replay, and checks in parallel) ran with 0 catalog errors, and both tables matched their topics exactly.
- ✅ Spark never holds storage credentials. Access is decided per table by the catalog, as AWS Lake Formation does.
- ✅ A web UI shows namespaces, tables, schemas and snapshots.
- ✅ Lighter than before: Lakekeeper about 45MB and Postgres about 90MB, against about 180MB for the reference catalog.
- ⚠️ Remote signing keeps a client inside its table only if the storage checks every part of a signed request. MinIO-style stores do not, and RustFS is probably the same, so a client could alter a signed request to reach another location. Locally, with one trusted client, this does not matter. A shared or exposed deployment needs storage that checks (AWS S3, Garage) or vended credentials.
- ⚠️ Tables are stored under IDs, not names (`s3://warehouse/<table id>/`), so renaming a table never moves files. Browsing the bucket shows IDs; the catalog and its UI show the names.
- ⚠️ Lakekeeper deletes a purged table's files in a background task, not during the drop.
- ⚠️ DuckDB does not support remote signing. Reading the tables from DuckDB needs its own read credentials (`client-managed`).
- ⚠️ More moving parts: three services instead of one, and a setup script.
- ⚠️ The tables of the previous catalog were not migrated. The lakehouse volumes were deleted together, and the bronze jobs read the topics again from the start.
