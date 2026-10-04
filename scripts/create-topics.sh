#!/bin/sh
# Creates the project's topics if they do not exist yet.
# Runs inside the redpanda container: `make topics`.
set -eu

RETENTION_MS=259200000 # 3 days, see docs/adr/0006-data-scope-and-retention.md

create() {
  name=$1
  partitions=$2
  if rpk topic describe "$name" >/dev/null 2>&1; then
    echo "topic $name already exists"
  else
    rpk topic create "$name" -p "$partitions" -c "retention.ms=$RETENTION_MS"
  fi
}

create wiki.raw 3
create wiki.dlq 1
