#!/bin/sh
# End-to-end check of the local lakehouse: `make check-lakehouse`.
# Asks the Iceberg catalog to create a table, checks that the table's metadata file
# landed in object storage, then drops the table and checks that its files are gone.
# Runs inside the object-store container, like create-buckets.sh: its curl signs S3
# requests completely, while the curl 7.88 of the dev container leaves out the
# x-amz-content-sha256 header that S3 requires.
set -eu

CATALOG=http://lakekeeper:8181/catalog
WAREHOUSE=wikipulse
STORAGE=http://localhost:9000
KEY=$RUSTFS_ACCESS_KEY
SECRET=$RUSTFS_SECRET_KEY
NAMESPACE=smoke_check
TABLE=check_$(date +%s)

step() { echo "--> $1"; }

step "catalog serves warehouse $WAREHOUSE"
# The catalog's config names the URL prefix of the warehouse; every table path uses it.
config=$(curl -sS --fail "$CATALOG/v1/config?warehouse=$WAREHOUSE")
prefix=$(printf '%s' "$config" | sed -n 's/.*"prefix" *: *"\([^"]*\)".*/\1/p')
if [ -z "$prefix" ]; then
  echo "FAIL: no prefix in the catalog's config: $config" >&2
  exit 1
fi
TABLES="$CATALOG/v1/$prefix/namespaces/$NAMESPACE/tables"

step "namespace $NAMESPACE exists"
status=$(curl -sS -o /dev/null -w '%{http_code}' -X POST "$CATALOG/v1/$prefix/namespaces" \
  -H 'Content-Type: application/json' -d "{\"namespace\": [\"$NAMESPACE\"]}")
# 200: created now. 409: it was already there.
case "$status" in
  200 | 409) ;;
  *) echo "FAIL: creating the namespace returned HTTP $status" >&2; exit 1 ;;
esac

drop_table() {
  curl -sS --fail -o /dev/null -X DELETE "$TABLES/$TABLE?purgeRequested=true"
}

# From here on a table may exist. If any step fails, drop it on the way out, so a failed
# check does not leave a table in the catalog and its files in storage.
trap 'echo "--> cleaning up after the failure"; drop_table || true' EXIT

step "create table $NAMESPACE.$TABLE"
response=$(curl -sS --fail -X POST "$TABLES" \
  -H 'Content-Type: application/json' -d "{
    \"name\": \"$TABLE\",
    \"schema\": {\"type\": \"struct\", \"schema-id\": 0, \"fields\": [
      {\"id\": 1, \"name\": \"id\", \"required\": true, \"type\": \"long\"}
    ]}
  }")

# The catalog answers with the location of the table's first metadata file.
location=$(printf '%s' "$response" | sed -n 's/.*"metadata-location" *: *"\([^"]*\)".*/\1/p')
if [ -z "$location" ]; then
  echo "FAIL: no metadata-location in the catalog's answer: $response" >&2
  exit 1
fi
echo "    metadata file: $location"

path=${location#s3://}
storage_status() {
  curl -sS -o /dev/null -w '%{http_code}' --head --aws-sigv4 aws:amz:us-east-1:s3 \
    --user "$KEY:$SECRET" "$STORAGE/$path"
}

step "metadata file is in object storage"
status=$(storage_status)
if [ "$status" != 200 ]; then
  echo "FAIL: the metadata file is not in storage (HTTP $status)" >&2
  exit 1
fi

step "drop the table and its files"
drop_table
trap - EXIT

# Lakekeeper deletes a purged table's files in a background task, so allow it a moment.
step "metadata file is gone from object storage"
for _ in $(seq 30); do
  status=$(storage_status)
  [ "$status" = 404 ] && break
  sleep 1
done
if [ "$status" != 404 ]; then
  echo "FAIL: 30s after the drop the metadata file is still in storage (HTTP $status)" >&2
  exit 1
fi

echo "OK: the catalog created a table in object storage, and dropping it removed its files"
