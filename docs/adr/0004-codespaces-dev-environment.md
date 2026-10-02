# ADR-0004: GitHub Codespaces as the dev environment

- **Status:** Accepted
- **Date:** 2026-10-02

## Context
The full stack (Redpanda + Spark + MinIO + Airflow) needs about 16GB of RAM, more than many laptops can spare. Anyone who wants to contribute or try the project should be able to run it with no setup.

## Decision
Develop in **GitHub Codespaces** on a 4-core / 16GB machine, defined by `.devcontainer/`. Use Docker-in-Docker to run the stack through docker-compose.

## Alternatives considered
- **Local Docker only:** works on a 16GB+ machine, but setup differs per OS and excludes smaller laptops. It stays possible through the same docker-compose file.
- **A cloud VM as the dev box:** more resources, but needs manual server management. Used for the always-on deployment instead (ADR-0005).
- **Managed SaaS per component:** less to run, but the repo stops being reproducible.

## Consequences
- ✅ One-click, reproducible environment for every contributor.
- ⚠️ The free quota is about 30 hours/month on a 4-core machine. Stop the codespace when done.
- ⚠️ Compose profiles and memory limits are required to stay within 16GB.
