# ADR-0010: RustFS and the reference REST catalog for the local lakehouse

> The catalog part of this decision is replaced by [ADR-0012](0012-lakekeeper-catalog.md) (Lakekeeper on Postgres), after the reference catalog's SQLite failed a commit under concurrent requests. RustFS stays the object store.

- **Status:** Accepted
- **Date:** 2026-10-20

## Context
[ADR-0003](0003-iceberg-table-format.md) chose Iceberg with a REST catalog locally and Glue in the cloud, and named MinIO as the local object store. Two things were left open or have changed since:

- **MinIO is no longer available as open source.** It stopped publishing free images and binaries in October 2025, and the project was archived in 2026. The `minio/minio` and `minio/mc` repositories on Docker Hub no longer exist. What remains are a community fork maintained mainly by one person (`pgsty/minio`, now Silo) and a third-party rebuild of the frozen code (Chainguard) that cannot be pinned to a version on its free tier.
- **The local catalog was an open question** in the design: Lakekeeper, Nessie or the reference implementation.

The local lakehouse is for development and tests. In the cloud, the tables live on S3 with the Glue catalog ([ADR-0005](0005-cloud-cost-strategy.md)).

## Decision
- **Object storage: RustFS** (`rustfs/rustfs:1.0.3`). It is S3-compatible, Apache-2.0, actively developed, and close to MinIO in configuration and web console.
- **Catalog: the Iceberg project's reference REST catalog** (`apache/iceberg-rest-fixture:1.10.1`). It keeps its state in a SQLite file.
- This is the same pair that Apache Iceberg uses in its own Spark and Flink quickstarts and in PyIceberg's integration tests. Our setup follows the most-used path for this combination.
- **Both keep their state on Docker volumes.** The catalog image keeps its SQLite file in `/tmp` by default, which is lost when the container is recreated while the data files remain in storage. The file is moved to a volume.
- **The services run behind the compose profile `lakehouse`** (`make lakehouse`), with memory limits of 512MB each, so that work on ingestion alone does not start them.
- **Everything talks to storage through the S3 API, and to the catalog through the Iceberg REST protocol.** Replacing either one is a configuration change, not a code change. Glue also offers an Iceberg REST endpoint.

## Alternatives considered
- **SeaweedFS:** Apache-2.0 and mature, developed since 2014. Community examples run it with Iceberg and Spark, but the Iceberg project itself does not use it, and some features are only in its paid edition. It is the first choice if RustFS proves unreliable, and the stronger choice for storage that must hold important data for a long time.
- **The MinIO fork (`pgsty/minio`, Silo):** the most familiar option, but it depends mainly on one maintainer who has committed to fixes only, with no new features.
- **Chainguard's MinIO image:** the same frozen code, with no upstream fixes and no version pinning on the free tier.
- **Garage:** light, but it leaves out S3 features such as versioning, and no Iceberg examples were found. AGPL-licensed.
- **Ceph RGW:** built for clusters of three or more servers; far too heavy for one development machine.
- **A managed Iceberg service (AWS S3 Tables, S3 + Glue, Cloudflare R2 Data Catalog):** no containers to run. But it saves little memory (Spark is the heavy part), tests and CI would need cloud credentials, and every run would cost money. The cloud setup comes in its own phase.
- **Lakekeeper as the catalog:** production-grade, with permissions, but it needs a Postgres container. Worth it when several users need access control.
- **Nessie as the catalog:** adds git-like branches of tables, which the project does not need, on a heavier service.

## Consequences
- ✅ The local stack matches Iceberg's own reference setup, so the official documentation and examples apply directly.
- ✅ Swapping storage or catalog is configuration only.
- ✅ `make check-lakehouse` verifies the pair end to end: the catalog creates a table, its metadata file is found in storage, and dropping the table removes the file. CI runs it on every pull request, so a broken image upgrade or catalog setting shows up at once.
- ✅ Both images are pinned by digest as well as by tag, so the same tag cannot bring different content (the reasoning of [ADR-0009](0009-ci-and-automated-review.md) for actions).
- ⚠️ RustFS reached 1.0 in September 2026. It is young, and we may meet its bugs early. Iceberg's own setup pins 1.0.0, which is the fallback if 1.0.3 shows a problem.
- ⚠️ The reference catalog has no users or permissions. Acceptable for local development only.
- ⚠️ Most older Iceberg tutorials show MinIO. Its settings map closely to RustFS, but not one to one.
- ⚠️ The catalog's state and the data files live on two separate volumes. They are deleted together by `make clean`. Deleting one without the other leaves tables that point to missing files, or files that no table points to.
- ⚠️ The `curl` in the development container (7.88) does not send the `x-amz-content-sha256` header that S3 requires, so S3 requests from scripts run inside the object store container, which has a newer `curl`.
