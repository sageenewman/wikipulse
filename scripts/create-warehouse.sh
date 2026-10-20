#!/bin/sh
# Bootstraps Lakekeeper once and creates the project's warehouse if it does not exist.
# Runs inside the object-store container (`make warehouse`, part of `make lakehouse`),
# which has curl and the storage credentials Lakekeeper needs.
# Decisions: docs/adr/0012-lakekeeper-catalog.md
set -eu

MANAGEMENT=http://lakekeeper:8181/management/v1
WAREHOUSE=wikipulse

# A new Lakekeeper must be bootstrapped once before it serves anything.
if curl -sS --fail "$MANAGEMENT/info" | grep -Eq '"bootstrapped": ?true'; then
  echo "catalog already bootstrapped"
else
  curl -sS --fail -o /dev/null -X POST "$MANAGEMENT/bootstrap" \
    -H 'Content-Type: application/json' -d '{"accept-terms-of-use": true}'
  echo "catalog bootstrapped"
fi

if curl -sS --fail "$MANAGEMENT/warehouse" | grep -Eq "\"name\": ?\"$WAREHOUSE\""; then
  echo "warehouse $WAREHOUSE already exists"
  exit 0
fi

# Tables live in the warehouse bucket (create-buckets.sh). STS is off: RustFS's STS is not
# tested with Lakekeeper, so clients use remote signing. Dropped tables are deleted at
# once ("hard"): this is development data, and soft deletion would keep it for days.
curl -sS --fail-with-body -o /dev/null -X POST "$MANAGEMENT/warehouse" \
  -H 'Content-Type: application/json' -d "{
    \"warehouse-name\": \"$WAREHOUSE\",
    \"storage-profile\": {
      \"type\": \"s3\",
      \"bucket\": \"warehouse\",
      \"endpoint\": \"http://object-store:9000\",
      \"region\": \"us-east-1\",
      \"path-style-access\": true,
      \"flavor\": \"s3-compat\",
      \"sts-enabled\": false,
      \"remote-signing-enabled\": true
    },
    \"storage-credential\": {
      \"type\": \"s3\",
      \"credential-type\": \"access-key\",
      \"aws-access-key-id\": \"$RUSTFS_ACCESS_KEY\",
      \"aws-secret-access-key\": \"$RUSTFS_SECRET_KEY\"
    },
    \"delete-profile\": {\"type\": \"hard\"}
  }"
echo "warehouse $WAREHOUSE created"
