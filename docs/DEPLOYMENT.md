# Deployment & Operations

Operational notes for running ReadPrism beyond a local dev stack.

## Production-shaped compose

`docker-compose.yml` is production-shaped and is what `docker compose up` runs.
Local-dev conveniences live in `docker-compose.dev.yml`, which is **opt-in**
(#106):

```bash
./scripts/init_env.sh                 # .env with generated secrets (idempotent)
docker compose up -d --build          # production mode
make up-dev                           # development: adds docker-compose.dev.yml
```

What the dev file changes:

- `APP_ENV=development` for every service: webhooks without a configured secret
  are accepted, operator metrics need no token, SQL is echoed, and an empty
  `SECRET_KEY` falls back to a public dev-only key. Never expose it.
- Backend runs `uvicorn --reload`.
- Meilisearch runs `MEILI_ENV=development`.
- Source is bind-mounted for hot edits.

Outside development the app refuses to start when `SECRET_KEY` (or
`REFRESH_SECRET_KEY`, if set) is empty, shorter than 32 characters, or a
published placeholder. Before a hosted deployment also set
`MAILGUN_WEBHOOK_SIGNING_KEY` (or the provider secret you use),
`MAILGUN_WEBHOOK_SIGNING_KEY` and SMTP credentials. See [`.env.example`](https://github.com/mohitmishra786/readprism/blob/main/.env.example).

## Upgrading to shared feeds (migration 0025)

Since #161 a feed followed by several users is polled once. Migration 0025
creates one `feeds` row per distinct feed URL from existing subscriptions and
tags stored items with it; per-user trust, tags and reading history are not
touched, and newsletter sources stay private. To preview the merge first:

```bash
make backup
docker compose exec backend python -m app.feeds_plan   # read-only
```

The backend then applies the migration on start (#126). `alembic downgrade
0024` reverses it; poll state remains mirrored on each source row.

## Workers & queues

Ingestion, embedding, and digest work run on separate Celery queues, one
`--pool=solo` worker container each (`worker-scrape`, `worker-embed`,
`worker-digest`) so a slow scrape can't starve digests. See
[ADR 0001](adr/0001-celery-solo-pool.md) for why each worker is single-process
and the migration path for higher throughput.

To add capacity, run more workers for the queue that is behind:
`docker compose up -d --scale worker-digest=4 --scale worker-embed=2`. Keep
exactly one `beat`. `GET /api/v1/metrics/queues` (metrics token) reports the
wait per queue, runtime per task, and the share of scheduled digests
delivered within `DIGEST_ON_TIME_SECONDS`. Targets and the load test
(`scripts/load_test_digests.py`) are in ADR 0001.

## Monitoring

- **Errors:** set `SENTRY_DSN` (backend) and `NEXT_PUBLIC_SENTRY_DSN` /
  `SENTRY_DSN` (frontend) to enable Sentry. No DSN = disabled.
- **Beat liveness:** the `beat` container has a healthcheck backed by a
  once-a-minute heartbeat task writing a short-TTL Redis key; a stalled beat
  (which would silently stop all ingestion/digests) turns the container
  unhealthy. Wire your orchestrator/alerting to container health.
- **Ranking quality:** `python scripts/ranking_eval.py --days 30` prints
  per-cohort read-prediction AUC.

## Rollback plan (launch-day safety, audit 15-2)

CI builds and tags images per commit. Keep the last-known-good tag pinned so a
launch-day regression is a 5-minute undo:

1. **Pin the good tag** before launch: note the currently-deployed image tag
   (e.g. the commit SHA) as `LAST_GOOD`.
2. **Revert:** re-deploy `LAST_GOOD` — `docker compose pull` the pinned tag (or
   `git checkout LAST_GOOD` for a build-on-host deploy) and
   `docker compose up -d` the affected services.
3. **Migrations:** the app only forward-migrates; a rollback keeps the newer
   schema (backward-compatible within a release). If a migration must be undone,
   `alembic downgrade -1` before deploying the older image.
4. **Status note:** post a short heads-up in GitHub Discussions if the hosted
   demo is affected.

Rehearse the revert once before launch — a rollback plan you haven't run isn't a
plan.

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

## Self-hosting with your own LLM key (BYO)

Self-hosted instances bring their own `GROQ_API_KEY` (and optionally an OpenAI
fallback), so heavy/niche readers pay their own inference bill directly — the
intended pressure-release for the worst-margin users (audit 13-3). The full
ranking engine and summarization run locally against your key; no ReadPrism
hosted service is involved. Tier limits (`FREE_MAX_SOURCES`,
`FREE_MAX_CREATORS`) are yours to configure or disable (set to 0) on your own
instance.

## Email deliverability (SPF / DKIM)

Digest emails carry one-click feedback links and an RFC 8058 unsubscribe
header, which only help if the mail actually arrives. For the domain that
sends (the SMTP `from` address):

1. **SPF:** a TXT record on the domain authorizing your SMTP provider's
   outbound servers (for Zoho: `v=spf1 include:zoho.com ~all`).
2. **DKIM:** enable it in the provider console and publish the provided
   CNAME/TXT keys, so signed headers survive forwarding.
3. **DMARC** (recommended): start with
   `v=DMARC1; p=none; rua=mailto:postmaster@yourdomain` and tighten once
   reports look clean.
4. Keep `EMAIL_PHYSICAL_ADDRESS` set — it is rendered in the footer
   (CAN-SPAM) — and leave the tracking pixel off (it is off by default and
   there is no switch to enable one).

## Hosted mode: verification, abuse limits, billing

These apply only with `DEPLOYMENT_MODE=hosted`; a self-hosted instance
ignores them.

- **Email verification (#175).** New accounts get a confirmation link and no
  other email until they click it: digests are built and readable in the app
  but not emailed, and newsletters sent to the account are dropped. A
  magic-link sign-in also confirms the address. Accounts that existed before
  migration 0027 count as confirmed. Signups are also capped per email domain
  per hour (`SIGNUP_PER_DOMAIN_PER_HOUR`, with 20x for large mail providers).
- **Abuse limits (#169).** Each account has an hourly fetch budget
  (`HOSTED_FETCH_BUDGET_PER_HOUR`). A feed poll counts against every account
  that follows the feed, and is skipped only when all of them are over
  budget. Each host is polled at most `HOSTED_HOST_POLLS_PER_HOUR` times
  across all accounts, and one account can follow at most
  `HOSTED_MAX_SOURCES_PER_HOST` feeds on the same host. Inbound newsletters
  are capped per account per day by count and size.
- **Billing (#173).** Billing runs through a merchant of record, so the
  provider handles VAT/GST. Steps:
  1. Set `BILLING_PROVIDER` to `lemonsqueezy` or `paddle`, and set
     `BILLING_WEBHOOK_SECRET`.
  2. Point the provider's webhook at
     `https://<api>/api/v1/billing/webhook/<provider>`, subscribed to the
     subscription events.
  3. Set the checkout links (Lemon Squeezy) or price ids (Paddle) in
     `BILLING_CHECKOUT_MONTHLY` and `BILLING_CHECKOUT_YEARLY`.
  4. List the variant or price ids that grant each plan in
     `BILLING_PRO_PRICE_IDS` and `BILLING_TEAM_PRICE_IDS`. An id that isn't
     listed never upgrades anyone.
  5. Paddle only: also set `BILLING_API_KEY`. Use `BILLING_SANDBOX=true`
     while testing.

  New accounts start a `BILLING_TRIAL_DAYS` trial with no card required.
  Prices and trial length are the #138 decision. Webhooks are verified,
  recorded once (a replay does nothing) and applied in order (an older event
  that arrives late can't bring back a cancelled plan). A plan lapses at its
  expiry date with no scheduled job.

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
