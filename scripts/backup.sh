#!/usr/bin/env bash
# ReadPrism backup/restore (RL-04).
#
# backup:  pg_dump (schema+data) + redis BGSAVE snapshot + .env (secrets!)
#          into a single timestamped tarball.
# restore: recreates the DB from a backup tarball into the running compose
#          stack (destructive: drops and recreates the database).
#
# Usage:
#   ./scripts/backup.sh  [output-dir]        (default: ./backups)
#   ./scripts/restore.sh backups/readprism-<ts>.tar.gz
#   ./scripts/restore_drill.sh [archive]     (non-destructive check, #209)
#
# Tarballs older than BACKUP_RETENTION_DAYS (default 14) in the output
# directory are deleted after a successful backup. Scheduling and off-box
# copies: docs/DEPLOYMENT.md#backups--restore.
set -euo pipefail
umask 077  # archive contains .env secrets
cd "$(dirname "$0")/.."

OUT_DIR="${1:-backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET="$OUT_DIR/readprism-$STAMP"

mkdir -p "$TARGET"

echo "==> dumping postgres (readprism)…"
docker compose exec -T db pg_dump -U readprism -d readprism -Fc > "$TARGET/db.dump"

echo "==> snapshotting redis…"
LASTSAVE_BEFORE="$(docker compose exec -T redis redis-cli --raw LASTSAVE | tr -d '[:space:]')"
docker compose exec -T redis redis-cli BGSAVE >/dev/null
# Poll LASTSAVE until it changes: BGSAVE is asynchronous (CodeRabbit).
for _ in $(seq 1 60); do
  LASTSAVE_NOW="$(docker compose exec -T redis redis-cli --raw LASTSAVE | tr -d '[:space:]')"
  [ "$LASTSAVE_NOW" != "$LASTSAVE_BEFORE" ] && break
  sleep 1
done
docker compose cp redis:/data/dump.rdb "$TARGET/redis.rdb" >/dev/null 2>&1 \
  || echo "  (no redis persistence file — skipping)"

if [ -f .env ]; then
  echo "==> copying .env (contains secrets — protect the tarball)…"
  cp .env "$TARGET/env"
fi

echo "==> writing manifest…"
{
  echo "created_utc=$STAMP"
  echo "postgres=pg_dump -Fc"
  echo "redis=$( [ -f "$TARGET/redis.rdb" ] && echo rdb || echo none )"
  echo "git_sha=$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
  echo "alembic_head=$(docker compose exec -T db psql -U readprism -d readprism -tAc \
    "SELECT version_num FROM alembic_version" 2>/dev/null | tr -d '[:space:]' || echo unknown)"
  # Row counts let restore_drill.sh check a restore without touching live data.
  for table in users sources content_items user_content_interactions interest_nodes digests; do
    echo "rows_$table=$(docker compose exec -T db psql -U readprism -d readprism -tAc \
      "SELECT count(*) FROM $table" 2>/dev/null | tr -d '[:space:]' || echo unknown)"
  done
} > "$TARGET/manifest.txt"

echo "==> bundling $TARGET.tar.gz"
tar -czf "$TARGET.tar.gz" -C "$OUT_DIR" "readprism-$STAMP"
rm -rf "$TARGET"
echo "backup complete: $TARGET.tar.gz"
# Tell the backup alert (#171) a backup succeeded. Best effort.
docker compose exec -T redis redis-cli SET backup:last_success "$(date -u +%s)" >/dev/null 2>&1 || true

RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
if [ "$RETENTION_DAYS" -gt 0 ] 2>/dev/null; then
  find "$OUT_DIR" -maxdepth 1 -name 'readprism-*.tar.gz' -type f -mtime "+$RETENTION_DAYS" -print -delete \
    | sed 's/^/pruned (older than '"$RETENTION_DAYS"' days): /'
fi
