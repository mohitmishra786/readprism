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
set -euo pipefail
cd "$(dirname "$0")/.."

OUT_DIR="${1:-backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET="$OUT_DIR/readprism-$STAMP"

mkdir -p "$TARGET"

echo "==> dumping postgres (readprism)…"
docker compose exec -T db pg_dump -U readprism -d readprism -Fc > "$TARGET/db.dump"

echo "==> snapshotting redis…"
docker compose exec -T redis redis-cli BGSAVE >/dev/null
sleep 1
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
} > "$TARGET/manifest.txt"

echo "==> bundling $TARGET.tar.gz"
tar -czf "$TARGET.tar.gz" -C "$OUT_DIR" "readprism-$STAMP"
rm -rf "$TARGET"
echo "backup complete: $TARGET.tar.gz"
