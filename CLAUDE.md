# CLAUDE.md

Guidance for Claude (and any other contributor) working in this repository. Read this first, every session.

## What this project is

**WikiPulse** is a real-time data platform that ingests the public Wikimedia edit stream (every edit on every Wikipedia, live), processes it into an Iceberg lakehouse, and detects **edit-rate spikes** that signal real-world breaking news. It also analyzes edit wars, bot vs. human activity, and Hebrew Wikipedia vs. other languages.

Full design: [docs/DESIGN.md](docs/DESIGN.md).

## How work is done here

This repository is built with Claude Code under the direction of the repository owner. The owner makes the decisions and approves every merge.

- **Explain before and after.** Before writing: say what you are about to build, why, and what the alternative was. After writing: walk the owner through what was written. The owner must be able to explain every line.
- **Ask before you push, and ask whenever you're unsure.** Before any push or PR, raise every open decision and wait for answers. Don't assume, and don't pick a default silently. An unanswered question stays open.
- **Small steps.** Work on one item from [docs/ROADMAP.md](docs/ROADMAP.md) at a time. Finish it, verify it, then move on.
- **Stay in scope.** If a task is not in the design or the roadmap, say so before doing it.
- **Ask before** adding a new tool or dependency that isn't in the design, or changing the architecture. Major decisions get an ADR in [docs/adr/](docs/adr/).

## Session checklist

**At the start of a session:**
1. Read [docs/ROADMAP.md](docs/ROADMAP.md) to see the current phase and the next open item.
2. Check the current git branch.

**At the end of a session (or when a task is done):**
1. Update [docs/ROADMAP.md](docs/ROADMAP.md): check off what's done and add items that came up.
2. If a design decision was made, write or update an ADR.

## Hard constraints

- **Do not run the heavy stack on a laptop.** Development happens in **GitHub Codespaces**, see [ADR-0004](docs/adr/0004-codespaces-dev-environment.md).
- **Memory is tight** for Redpanda + Spark + Airflow + MinIO. Every container in docker-compose must have a memory limit. Use compose **profiles** so only the needed services run.
- **AWS costs must stay near zero.** Use only S3, Glue Data Catalog and Athena (pay-per-use). **Never** provision MSK, EMR, NAT Gateways, or always-on EC2 without asking first. Budget alerts must exist before any `terraform apply`. Run `terraform destroy` after demo sessions. See [ADR-0005](docs/adr/0005-cloud-cost-strategy.md).
- **No secrets in the repo.** Use `.env` (gitignored) and `.env.example`.

## Architecture (short)

```
Wikimedia SSE → Python producer → Redpanda (Kafka API, Schema Registry)
  → Spark Structured Streaming → Iceberg on S3/MinIO (bronze → silver → gold)
  → dbt + DuckDB → Streamlit dashboard
Airflow: dbt runs, Iceberg maintenance, backfills
Prometheus + Grafana: lag, throughput, latency, DLQ
Terraform: AWS (S3 + Glue + Athena) | GitHub Actions: CI
```

## Repo layout

```
.claude/agents/       Agent definitions (the code reviewer)
.devcontainer/        Codespaces config
.github/workflows/    CI
ingestion/            SSE producer, recorder and replay
streaming/            Spark Structured Streaming jobs
analytics/dbt/        dbt project
orchestration/dags/   Airflow DAGs
dashboard/            Streamlit app
infra/terraform/      AWS infrastructure
monitoring/           Prometheus and Grafana config
data/samples/         Recorded events for tests and replay (small files only)
docs/                 Design, roadmap, engineering and review guides, ADRs
```

Some folders don't exist yet. Create them when their phase starts.

## Data source notes

Details: [docs/DATA_SOURCE.md](docs/DATA_SOURCE.md).

- Stream: `https://stream.wikimedia.org/v2/stream/recentchange` (Server-Sent Events).
- Wikimedia **requires a descriptive `User-Agent`** header with contact info, or requests may be blocked.
- To resume after a disconnect, send the **`Last-Event-ID`** header. Delivery is at-least-once, so we **deduplicate downstream by `meta.id`**.
- Event schema: https://schema.wikimedia.org/#!/primary/jsonschema/mediawiki/recentchange
- Most events are not human edits to Wikipedia articles: about half the stream comes from Wikimedia Commons, and bots and Wikidata add a large share. Keep the `bot` flag and the `wiki` field; don't drop them at ingestion.

## Engineering conventions

**Code follows [docs/ENGINEERING.md](docs/ENGINEERING.md).** Read it before writing code. In short:

- **Python 3.12**, type hints everywhere, `ruff` (lint + format), `mypy`, `pytest`.
- Configuration comes from environment variables, loaded through a settings module (pydantic-settings). No hardcoded hosts or ports.
- Keep pure logic (parsing, dedup keys, spike scoring) separate from I/O so it can be unit-tested.
- Streaming code is tested with **recorded samples + replay mode**, not against the live stream.
- Logs are structured (JSON), and every service exposes metrics.
- **OOP style:** classes where there is state, a lifecycle or an external boundary; protocols at boundaries; plain functions for pure logic; no inheritance for reuse.

## Git conventions

- `main` is always working. All work happens on branches and is merged through a PR.
- Branch names: `feat/<short-name>`, `fix/<short-name>`, `chore/<short-name>`, `docs/<short-name>`, `infra/<short-name>`.
- Commits follow **Conventional Commits**: `feat(ingestion): add SSE reconnect with Last-Event-ID`.
- The PR description answers four questions: why the change exists, what changed, how it was verified, and what is not included ([ENGINEERING.md](docs/ENGINEERING.md), section 7).
- Never commit or push without the owner's go-ahead.
- **Never merge a PR yourself.** Open the PR, explain it, and wait for the owner to review and say "merge".

## Code review

Reviews follow [docs/CODE_REVIEW.md](docs/CODE_REVIEW.md). Write code expecting an independent review.

1. Claude opens the PR with a description that answers the four questions above.
2. The reviewer agent ([.claude/agents/code-reviewer.md](.claude/agents/code-reviewer.md)) examines it and only writes findings. It is read-only and never changes code.
3. Claude fixes, and posts a "changes after review" summary using the template in CODE_REVIEW.md.
4. The owner alone approves the merge, after seeing both summaries.

## Commands

Run inside the codespace. `make help` lists them all.

| Command | What it does |
|---|---|
| `make up` / `make down` | Start the stack (Redpanda + Console) and create the topics / stop it |
| `make ps` / `make logs` | Service status / logs |
| `make clean` | Stop and delete data volumes |
| `make topics` | Create the Kafka topics if they do not exist |
| `make ingest` | Run the live producer: Wikimedia stream to Kafka |
| `make record` / `make replay` | Save the stream to a file / publish a recording to Kafka |
| `make check-gaps` | Check the raw topic for lost or duplicated events |
| `make sync` | Install Python dependencies with uv |
| `make lint` / `make fmt` / `make typecheck` / `make test` | ruff / ruff format / mypy / pytest |
