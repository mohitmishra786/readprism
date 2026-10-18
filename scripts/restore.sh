#!/usr/bin/env bash
# Restore a ReadPrism backup tarball (RL-04). DESTRUCTIVE for the target DB.
set -euo pipefail
cd "$(dirname "$0")/.."

ARCHIVE="${1:?usage: restore.sh backups/readprism-<ts>.tar.gz}"
[ -f "$ARCHIVE" ] || { echo "no such archive: $ARCHIVE"; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
tar -xzf "$ARCHIVE" -C "$TMP"
SRC="$(find "$TMP" -mindepth 1 -maxdepth 1 -type d | head -1)"
[ -f "$SRC/db.dump" ] || { echo "archive has no db.dump"; exit 1; }

echo "==> stopping write paths (workers, backend)…"
docker compose stop backend worker-scrape worker-embed worker-digest beat >/dev/null 2>&1 || true

echo "==> dropping and recreating database readprism…"
docker compose exec -T db psql -U readprism -d postgres \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='readprism' AND pid <> pg_backend_pid();" \
  -c "DROP DATABASE IF EXISTS readprism;" \
  -c "CREATE DATABASE readprism;"
docker compose exec -T db psql -U readprism -d readprism -c "CREATE EXTENSION IF NOT EXISTS vector;" >/dev/null

echo "==> restoring schema + data…"
# The dump lives on the host: stream it into the container via stdin.
docker compose exec -T db pg_restore -U readprism -d readprism --no-owner --no-privileges < "$SRC/db.dump" \
  || { echo "pg_restore reported errors — inspect above"; exit 1; }

if [ -f "$SRC/redis.rdb" ]; then
  echo "==> restoring redis snapshot…"
  docker compose stop redis >/dev/null 2>&1 || true
  # With AOF on (#204), Redis starts from the AOF and ignores dump.rdb, even
  # when the AOF directory is missing (it starts empty). So: drop the old AOF,
  # load the snapshot in a one-off Redis with AOF off, switch AOF on there
  # (Redis rewrites the AOF from the loaded data), then start the service.
  docker compose run --rm --no-deps --entrypoint sh redis -c "rm -rf /data/appendonlydir" >/dev/null 2>&1 || true
  docker compose cp "$SRC/redis.rdb" redis:/data/dump.rdb >/dev/null
  docker compose run -d --no-deps --name readprism-redis-restore redis \
    redis-server --appendonly no >/dev/null
  for _ in $(seq 1 30); do
    docker exec readprism-redis-restore redis-cli ping 2>/dev/null | grep -q PONG && break
    sleep 1
  done
  docker exec readprism-redis-restore redis-cli config set appendonly yes >/dev/null
  for _ in $(seq 1 60); do
    info=$(docker exec readprism-redis-restore redis-cli info persistence)
    if echo "$info" | grep -q "aof_enabled:1" && echo "$info" | grep -q "aof_rewrite_in_progress:0" \
      && ! echo "$info" | grep -q "aof_rewrite_scheduled:1"; then
      break
    fi
    sleep 1
  done
  docker exec readprism-redis-restore redis-cli shutdown >/dev/null 2>&1 || true
  docker rm -f readprism-redis-restore >/dev/null 2>&1 || true
  docker compose start redis >/dev/null
fi

echo "==> verifying alembic head matches the manifest…"
EXPECTED="$(grep alembic_head "$SRC/manifest.txt" 2>/dev/null | cut -d= -f2 || echo unknown)"
ACTUAL="$(docker compose exec -T db psql -U readprism -d readprism -tAc \
  "SELECT version_num FROM alembic_version" | tr -d '[:space:]')"
echo "  manifest=$EXPECTED restored=$ACTUAL"
[ "$EXPECTED" = "unknown" ] || [ "$EXPECTED" = "$ACTUAL" ] \
  || { echo "HEAD MISMATCH — run 'docker compose run --rm backend alembic upgrade head' to roll forward."; exit 1; }

echo "==> restarting services…"
docker compose up -d backend worker-scrape worker-embed worker-digest beat >/dev/null
echo "restore complete."
