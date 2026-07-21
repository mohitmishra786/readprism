#!/usr/bin/env bash
# Nightly Postgres backup (audit 07-3). The behavioural history IS the product,
# so a single volume loss must not be total loss.
#
# Usage (host cron, daily):
#   BACKUP_DIR=/var/backups/readprism ./backend/scripts/backup.sh
#
# Restores are documented in docs/DEPLOYMENT.md.
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
DB_SERVICE="${DB_SERVICE:-db}"
DB_USER="${POSTGRES_USER:-readprism}"
DB_NAME="${POSTGRES_DB:-readprism}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"

mkdir -p "$BACKUP_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$BACKUP_DIR/readprism-$STAMP.sql.gz"

echo "Dumping $DB_NAME -> $OUT"
# Custom-format-free plain SQL, gzipped, streamed straight out of the db container.
docker compose exec -T "$DB_SERVICE" pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$OUT"

# Prune old backups.
find "$BACKUP_DIR" -name 'readprism-*.sql.gz' -type f -mtime "+$RETENTION_DAYS" -delete

echo "Backup complete: $OUT"
echo "Kept backups newer than ${RETENTION_DAYS}d in $BACKUP_DIR"
