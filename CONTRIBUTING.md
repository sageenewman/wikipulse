# Contributing

## Getting started

The project is developed in GitHub Codespaces (4-core / 16GB). Open the repo in a codespace and the dev container sets everything up. Setup commands will be listed in the [README](README.md) as they land.

Before starting work, read the [design document](docs/DESIGN.md) and check the [roadmap](docs/ROADMAP.md) for the current phase.

## Workflow

- `main` is always working. All work happens on a branch and is merged through a pull request.
- One branch = one focused piece of work, usually one roadmap item.
- The PR description explains **why** the change exists, what changed, and any follow-ups.
- CI must be green before merging.

### Branch names

| Prefix | Use for |
|---|---|
| `feat/` | New functionality |
| `fix/` | Bug fixes |
| `chore/` | Tooling, dependencies, config |
| `infra/` | Docker, Terraform, CI |
| `docs/` | Documentation only |

### Commit messages

[Conventional Commits](https://www.conventionalcommits.org/): `type(scope): summary`

```
feat(ingestion): add SSE reconnect with Last-Event-ID
fix(streaming): dedupe on meta.id instead of revision id
```

## Code conventions

The full rules are in [docs/ENGINEERING.md](docs/ENGINEERING.md). In short:

- **Python 3.12**, type hints everywhere. `ruff` for lint and format, `mypy` in strict mode, `pytest` for tests.
- Pure logic is kept apart from I/O. External systems sit behind protocols and are passed in.
- A change in behaviour comes with a test.
- No error is swallowed.
- Configuration comes from environment variables. No secrets in the repo.

## Code review

Every PR is reviewed before it is merged, following [docs/CODE_REVIEW.md](docs/CODE_REVIEW.md):

1. The reviewer examines the change and reports findings. The reviewer never changes code.
2. The author answers every finding and posts a summary of the changes made after the review.
3. The repository owner approves the merge, after reading the PR description and that summary.

## Design decisions

Significant decisions (a new tool, a change in architecture) are recorded as an ADR in [docs/adr/](docs/adr/). Copy the template and use the next number.

## Resource and cost limits

- Every container in docker-compose has a memory limit. Use compose profiles to run only what you need.
- Cloud resources are limited to pay-per-use services (S3, Glue, Athena). See [ADR-0005](docs/adr/0005-cloud-cost-strategy.md).
