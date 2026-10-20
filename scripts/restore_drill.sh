#!/usr/bin/env bash
# Restore drill (#209): prove a backup restores, WITHOUT touching live data.
#
# Restores the backup's database dump into a throwaway database
# (readprism_restore_drill) in the running db container, compares row counts
# with the backup's manifest, and drops the throwaway database.
#
# Usage:
#   ./scripts/restore_drill.sh                       # newest backups/*.tar.gz
#   ./scripts/restore_drill.sh /var/backups/readprism/readprism-<ts>.tar.gz
# Exit status 0 = the backup restores and its counts match.
set -euo pipefail
cd "$(dirname "$0")/.."

ARCHIVE="${1:-$(ls -t backups/readprism-*.tar.gz 2>/dev/null | head -1)}"
[ -n "$ARCHIVE" ] && [ -f "$ARCHIVE" ] || { echo "no backup archive found"; exit 1; }
DRILL_DB=readprism_restore_drill

TMP="$(mktemp -d)"
cleanup() {
  rm -rf "$TMP"
  docker compose exec -T db psql -U readprism -d postgres -qc "DROP DATABASE IF EXISTS $DRILL_DB;" >/dev/null 2>&1 || true
}
trap cleanup EXIT
tar -xzf "$ARCHIVE" -C "$TMP"
SRC="$(find "$TMP" -mindepth 1 -maxdepth 1 -type d | head -1)"
[ -f "$SRC/db.dump" ] || { echo "archive has no db.dump"; exit 1; }

echo "==> drill: restoring $ARCHIVE into $DRILL_DB (live data untouched)"
docker compose exec -T db psql -U readprism -d postgres -qc "DROP DATABASE IF EXISTS $DRILL_DB;" -c "CREATE DATABASE $DRILL_DB;" >/dev/null
docker compose exec -T db psql -U readprism -d "$DRILL_DB" -qc "CREATE EXTENSION IF NOT EXISTS vector;" >/dev/null
docker compose exec -T db pg_restore -U readprism -d "$DRILL_DB" --no-owner --no-privileges < "$SRC/db.dump" \
  || { echo "drill FAILED: pg_restore reported errors"; exit 1; }

failed=0
while IFS='=' read -r key expected; do
  case "$key" in rows_*) ;; *) continue ;; esac
  table="${key#rows_}"
  # </dev/null: docker compose exec would otherwise swallow the rest of the manifest.
  actual="$(docker compose exec -T db psql -U readprism -d "$DRILL_DB" -tAc "SELECT count(*) FROM $table" </dev/null | tr -d '[:space:]')"
  if [ "$expected" = "unknown" ] || [ "$actual" = "$expected" ]; then
    echo "  ok   $table: $actual rows"
  else
    echo "  FAIL $table: $actual rows restored, backup had $expected"
    failed=1
  fi
done < "$SRC/manifest.txt"
grep -q '^rows_' "$SRC/manifest.txt" || echo "  (older backup without row counts: restore succeeded, counts not checked)"

[ "$failed" = 0 ] && echo "drill passed: $ARCHIVE restores cleanly" || { echo "drill FAILED"; exit 1; }
