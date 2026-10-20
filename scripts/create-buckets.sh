#!/bin/sh
# Creates the project's buckets if they do not exist.
# Runs inside the object-store container: `make buckets`.
# The credentials come from that container's environment.
set -eu

ENDPOINT=http://localhost:9000

s3() {
  curl -sS --fail --aws-sigv4 aws:amz:us-east-1:s3 \
    --user "$RUSTFS_ACCESS_KEY:$RUSTFS_SECRET_KEY" "$@"
}

ensure() {
  name=$1
  if s3 -o /dev/null --head "$ENDPOINT/$name" 2>/dev/null; then
    echo "bucket $name already exists"
  else
    s3 -o /dev/null -X PUT "$ENDPOINT/$name"
    echo "bucket $name created"
  fi
}

# Every Iceberg table lives under this bucket (the warehouse's storage profile in
# scripts/create-warehouse.sh).
ensure warehouse
