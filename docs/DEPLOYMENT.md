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
- Source is bind-mounted for hot edits.

Outside development the app refuses to start when `SECRET_KEY` (or
`REFRESH_SECRET_KEY`, if set) is empty, shorter than 32 characters, or a
published placeholder. Before a hosted deployment also set
`MAILGUN_WEBHOOK_SIGNING_KEY` (or the provider secret you use),
SMTP credentials. See [`.env.example`](https://github.com/mohitmishra786/readprism/blob/main/.env.example).

For upgrades between versions, follow [UPGRADING.md](UPGRADING.md).

## All-in-one image (3 containers)

For homelab app stores (Unraid, CasaOS, TrueNAS) and small installs,
`compose.aio.yml` runs ReadPrism as three containers: `readprism` plus
Postgres and Redis.

```bash
./scripts/init_env.sh
docker compose -f compose.aio.yml up -d      # pulls ghcr.io/…/readprism-aio
# or build from this checkout:
docker compose -f compose.aio.yml up -d --build
```

The `readprism` container (`deploy/aio/Dockerfile`) supervises, with
s6-overlay: a one-shot migration, then the API, one solo-pool worker per queue
(scrape, embed, digest, as in the multi-container install), a single beat and
the web app. Its healthcheck requires every process to be up, the API and web
app to answer and the beat heartbeat to be fresh. A failed migration stops
the container.

- Run **one** copy per database: a second copy would start a second beat.
  To scale workers, use the multi-container `docker-compose.yml`.
- Rendered-page extraction (browserless) is not included; JS-only pages keep
  their feed summary.
- Build with `--build-arg LITE=1` for the image without torch.
- Idle memory, measured on 2026-10-20 (lite image, arm64, fresh instance, no
  sources yet): `readprism` 419 MiB, Postgres 55 MiB, Redis 11 MiB, about
  485 MiB in total. The full image also loads the sentence-transformers model
  (the API does so at start-up), so it needs more; that was not measured.

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
- **In-app health banner (#234):** the instance owner (the first account)
  sees a red banner when the scheduler or a worker queue stopped (each queue
  runs a heartbeat every 5 minutes; reported after
  `HEALTH_WORKER_STALE_MINUTES`, default 30), a queue has more than
  `HEALTH_QUEUE_BACKLOG` jobs waiting, feeds produced nothing for
  `HEALTH_INGEST_STALE_HOURS` (default 6), or the last LLM call failed. The
  data is at `GET /api/v1/metrics/instance-health`; other accounts get an
  empty list.
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

The interest graph and reading history are the product: back them up, keep a
copy off the machine, and rehearse a restore.

**What a backup contains** (`scripts/backup.sh`, also `make backup`): one
`readprism-<UTC time>.tar.gz` with the Postgres dump (`pg_dump -Fc`), a Redis
snapshot (sessions, sign-in links), your `.env` (**secrets**: store the
archive like a password) and a manifest with the schema version and row
counts. After each run, archives older than `BACKUP_RETENTION_DAYS` (default
14) in the same folder are deleted.

### Schedule it

Pick one. Both run nightly at 03:15 from the directory with your
`docker-compose.yml`.

cron (`crontab -e`):

```cron
15 3 * * * cd /opt/readprism && ./scripts/backup.sh /var/backups/readprism >> /var/log/readprism-backup.log 2>&1
```

systemd timer (`/etc/systemd/system/readprism-backup.service` and `.timer`):

```ini
# readprism-backup.service
[Unit]
Description=ReadPrism backup
After=docker.service

[Service]
Type=oneshot
WorkingDirectory=/opt/readprism
Environment=BACKUP_RETENTION_DAYS=14
ExecStart=/opt/readprism/scripts/backup.sh /var/backups/readprism
```

```ini
# readprism-backup.timer
[Unit]
Description=Nightly ReadPrism backup

[Timer]
OnCalendar=*-*-* 03:15:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now readprism-backup.timer
systemctl list-timers readprism-backup.timer   # next run
```

### Copy it off the box

A backup on the same disk doesn't survive that disk. Add one of these after
the backup (in the cron line with `&&`, or as `ExecStartPost=` in the unit).

restic (encrypted, deduplicated; any S3/B2/SFTP repository):

```bash
export RESTIC_REPOSITORY=s3:s3.amazonaws.com/my-bucket/readprism RESTIC_PASSWORD_FILE=/root/.restic-pass
restic backup /var/backups/readprism && restic forget --keep-daily 14 --keep-weekly 8 --prune
```

rclone (plain copy to any configured remote; the archive holds secrets, so
use an encrypted `crypt` remote):

```bash
rclone copy /var/backups/readprism remote-crypt:readprism-backups --max-age 48h
```

### Rehearse a restore (monthly)

```bash
make restore-drill                                     # newest backup in ./backups
./scripts/restore_drill.sh /var/backups/readprism/readprism-<ts>.tar.gz
```

The drill restores the dump into a throwaway database
(`readprism_restore_drill`), checks every table's row count against the
backup's manifest, and drops it. Your live data is not touched; exit status
0 means the backup restores. CI runs the same drill on every change to the
backup scripts. To rehearse an off-box copy, download it first (`restic
restore latest --target /tmp/rp`) and point the drill at the archive.

### Restore for real

**Destructive**: this replaces the live database and Redis data.

```bash
./scripts/restore.sh /var/backups/readprism/readprism-<ts>.tar.gz   # or: make restore FILE=...
```

It stops the API and workers, recreates the database from the dump, loads
the Redis snapshot, and starts everything again; migrations then run on
boot. The archive's `env` file holds the `.env` from backup time: compare it
with yours if you are restoring onto a new machine.

## First-boot setup screen

On a fresh instance the sign-up page creates the **owner account** (the first
account) and then opens **Instance setup** (`/admin/setup`, also linked from
Preferences). There the owner can enter the LLM key, base URL and models,
SMTP details and who may sign up (`closed`, `invite` with codes, `open`), with
a **Test** button for the key and a test email to the owner's address. No file
editing is needed.

- Values are stored encrypted (Fernet) in the `instance_settings` table with a
  key derived from `SECRETS_ENCRYPTION_KEY`, which `scripts/init_env.sh`
  generates. Without it the screen is read-only. Changing that key makes the
  saved values unreadable; re-enter them.
- Anything set in the environment or `.env` wins and shows as locked.
- Secrets are write-only: the API reports only whether one is saved.
- The API applies changes at once; workers pick them up within a minute.

## Self-hosting with your own LLM key (BYO)

Self-hosted instances bring their own `LLM_API_KEY` (or the legacy, deprecated
`GROQ_API_KEY` — removed in v0.3; and optionally an OpenAI fallback), so
heavy/niche readers pay their own inference bill directly — the
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
