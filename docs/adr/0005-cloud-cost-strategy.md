# ADR-0005: Near-zero-cost cloud strategy

- **Status:** Accepted
- **Date:** 2026-10-02

## Context
The project should run on real cloud infrastructure, managed as code, without ongoing cost. Managed streaming and compute (MSK, EMR, always-on EC2) cost tens to hundreds of dollars a month.

## Decision
- **AWS, pay-per-use only:** S3 (Iceberg storage), Glue Data Catalog, Athena, IAM. All managed with Terraform.
- **Compute:** run Redpanda + Spark + Airflow on an **Oracle Cloud Always Free** VM (ARM, up to 4 cores / 24GB).
- **Guardrails:** AWS budget alert at $5 before the first `apply`. No NAT Gateway, MSK or EMR. `terraform destroy` after demo sessions.

## Alternatives considered
- **All-AWS (MSK + EMR/EKS):** the most conventional setup, but costly.
- **AWS free-tier EC2 only:** too small (about 1GB RAM) for the stack.

## Consequences
- ✅ Real Terraform/AWS infrastructure with costs in cents.
- ⚠️ A hybrid setup: S3 access from the Oracle VM needs IAM credentials handled safely.
- ⚠️ ARM images: every container must support `linux/arm64`.
