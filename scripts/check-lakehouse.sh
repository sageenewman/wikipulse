#!/bin/sh
# End-to-end check of the local lakehouse: `make check-lakehouse`.
# Asks the Iceberg catalog to create a table, checks that the table's metadata file
# landed in object storage, then drops the table and checks that its files are gone.
# Runs inside the object-store container, like create-buckets.sh: its curl signs S3
# requests completely, while the curl 7.88 of the dev container leaves out the
# x-amz-content-sha256 header that S3 requires.
set -eu

CATALOG=http://iceberg-rest:8181
STORAGE=http://localhost:9000
KEY=$RUSTFS_ACCESS_KEY
SECRET=$RUSTFS_SECRET_KEY
NAMESPACE=smoke_check
TABLE=check_$(date +%s)

step() { echo "--> $1"; }

step "catalog answers at $CATALOG"
curl -sS --fail -o /dev/null "$CATALOG/v1/config"

step "namespace $NAMESPACE exists"
status=$(curl -sS -o /dev/null -w '%{http_code}' -X POST "$CATALOG/v1/namespaces" \
  -H 'Content-Type: application/json' -d "{\"namespace\": [\"$NAMESPACE\"]}")
# 200: created now. 409: it was already there.
case "$status" in
  200 | 409) ;;
  *) echo "FAIL: creating the namespace returned HTTP $status" >&2; exit 1 ;;
esac

drop_table() {
  curl -sS --fail -o /dev/null -X DELETE \
    "$CATALOG/v1/namespaces/$NAMESPACE/tables/$TABLE?purgeRequested=true"
}

# From here on a table may exist. If any step fails, drop it on the way out, so a failed
# check does not leave a table in the catalog and its files in storage.
trap 'echo "--> cleaning up after the failure"; drop_table || true' EXIT

step "create table $NAMESPACE.$TABLE"
response=$(curl -sS --fail -X POST "$CATALOG/v1/namespaces/$NAMESPACE/tables" \
  -H 'Content-Type: application/json' -d "{
    \"name\": \"$TABLE\",
    \"schema\": {\"type\": \"struct\", \"schema-id\": 0, \"fields\": [
      {\"id\": 1, \"name\": \"id\", \"required\": true, \"type\": \"long\"}
    ]}
  }")

# The catalog answers with the location of the table's first metadata file,
# for example s3://warehouse/smoke_check/check_1/metadata/00000-<uuid>.metadata.json
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

step "metadata file is gone from object storage"
status=$(storage_status)
if [ "$status" != 404 ]; then
  echo "FAIL: the table was dropped but its metadata file is still in storage (HTTP $status)" >&2
  exit 1
fi

echo "OK: the catalog created a table in object storage, and dropping it removed its files"
