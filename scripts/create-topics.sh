#!/bin/sh
# Creates the project's topics if they do not exist, and applies their retention.
# Runs inside the redpanda container: `make topics`.
# Retention values: docs/adr/0006-data-scope-and-retention.md
set -eu

DAY_MS=86400000

ensure() {
  name=$1
  partitions=$2
  retention_ms=$3
  if rpk topic describe "$name" >/dev/null 2>&1; then
    echo "topic $name already exists"
  else
    rpk topic create "$name" -p "$partitions"
  fi
  # Applied on every run, so a changed value reaches existing topics too.
  rpk topic alter-config "$name" --set "retention.ms=$retention_ms"
}

ensure wiki.raw 3 $((3 * DAY_MS))
# Dead-lettered events are evidence for debugging, so they are kept longer.
ensure wiki.dlq 1 $((14 * DAY_MS))
