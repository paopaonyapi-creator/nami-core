#!/bin/bash
set -euo pipefail

# Phase 34: Promote prod schema -> staging weekly (schema only, NO data)

PROD_DB="glodbyproza"
PROD_USER="postgres" # usually run via sudo -u postgres
STAGING_DB="nami_staging"
STAGING_USER="nami_staging"
STAGING_HOST="127.0.0.1"
STAGING_PORT="5433"

echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] Starting staging schema sync..."

# 1. Dump prod schema (no data)
DUMP_FILE="/tmp/nami_prod_schema.sql"
echo "Dumping prod schema from $PROD_DB..."
pg_dump -U "$PROD_USER" -s -x -O "$PROD_DB" > "$DUMP_FILE"

# 2. Reset staging DB (drop and recreate schema 'public')
echo "Resetting staging DB..."
export PGPASSWORD="staging_password"
psql -h "$STAGING_HOST" -p "$STAGING_PORT" -U "$STAGING_USER" -d "$STAGING_DB" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

# 3. Apply schema to staging
echo "Applying schema to staging DB..."
psql -h "$STAGING_HOST" -p "$STAGING_PORT" -U "$STAGING_USER" -d "$STAGING_DB" < "$DUMP_FILE"

rm "$DUMP_FILE"
echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] Staging schema sync complete."
