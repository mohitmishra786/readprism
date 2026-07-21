# Deployment & Operations

Operational notes for running ReadPrism beyond a local dev stack.

## Production-shaped compose

`docker-compose.yml` is production-shaped; `docker-compose.override.yml` adds
local-dev conveniences and is loaded automatically by `docker compose` on your
machine. In production, run without the override:

```bash
docker compose -f docker-compose.yml up -d
```

Differences the override applies for dev only:

- Backend runs `uvicorn --reload` (base has no reload).
- Meilisearch runs `MEILI_ENV=development` (base runs `production`, which
  enforces the master key so search isn't left open).
- Source is bind-mounted for hot edits.

Before any hosted deployment, set real values for `SECRET_KEY` (the app refuses
to boot with the default outside development), `MAILGUN_WEBHOOK_SIGNING_KEY`,
`MEILISEARCH_MASTER_KEY`, and SMTP credentials. See [`.env.example`](../.env.example).

## Workers & queues

Ingestion, embedding, and digest work run on separate Celery queues, one
`--pool=solo` worker container each (`worker-scrape`, `worker-embed`,
`worker-digest`) so a slow scrape can't starve digests. See
[ADR 0001](adr/0001-celery-solo-pool.md) for why each worker is single-process
and the migration path for higher throughput.

## Monitoring

- **Errors:** set `SENTRY_DSN` (backend) and `NEXT_PUBLIC_SENTRY_DSN` /
  `SENTRY_DSN` (frontend) to enable Sentry. No DSN = disabled.
- **Beat liveness:** the `beat` container has a healthcheck backed by a
  once-a-minute heartbeat task writing a short-TTL Redis key; a stalled beat
  (which would silently stop all ingestion/digests) turns the container
  unhealthy. Wire your orchestrator/alerting to container health.
- **Ranking quality:** `python scripts/ranking_eval.py --days 30` prints
  per-cohort read-prediction AUC.

## Backups & restore

The interest graph and reading history are the product; back the database up.

**Nightly backup** (host cron):

```bash
BACKUP_DIR=/var/backups/readprism ./backend/scripts/backup.sh
```

This `pg_dump`s the `readprism` database to a timestamped gzip and prunes dumps
older than `BACKUP_RETENTION_DAYS` (default 14).

**Restore** into a fresh database:

```bash
# 1. Ensure the db container is up and the target DB exists + has pgvector.
docker compose exec -T db psql -U readprism -c "CREATE DATABASE readprism;" || true
docker compose exec -T db psql -U readprism -d readprism -c "CREATE EXTENSION IF NOT EXISTS vector;"

# 2. Load the dump.
gunzip -c /var/backups/readprism/readprism-YYYYMMDDTHHMMSSZ.sql.gz \
  | docker compose exec -T db psql -U readprism -d readprism

# 3. Bring migrations to head (no-op if the dump was current).
docker compose exec -T backend alembic upgrade head
```

Test a restore periodically — an untested backup is not a backup.

## Minimum host sizing

The sentence-transformer model loads into memory in the API and each worker.

| Scale | RAM | Notes |
|---|---|---|
| Local / demo | 4 GB | The full stack; model load ~60–90s per container on first boot |
| Small hosted (≤50 users, ≤100 sources) | 8 GB | pgvector + Redis + Browserless + embedding model across API and 3 workers |
| Growing | 16 GB+ | Consider a single shared embedding service and managed Postgres |

CPU is the embedding/ingestion bottleneck (embeddings run on CPU by default;
set `EMBEDDING_DEVICE=cuda` if a GPU is available). Validate the 30-minute
ingestion SLA under load before launch (see `scripts/loadtest_ingestion.py`).
