# Upgrading

<p class="lead">Every upgrade follows the same four steps. Version-specific
notes follow.</p>

## The steps

1. **Back up and rehearse the restore.**

    ```bash
    ./scripts/backup.sh /var/backups/readprism
    ./scripts/restore_drill.sh   # restores into a throwaway DB, checks counts, drops it
    ```

    !!! tip "Don't skip the drill"
        It is how you know the rollback below will work. See
        [Backups & restore](DEPLOYMENT.md#backups-restore).

2. **Read the notes for every version you are crossing** (below, and the
    [release notes](releases/)). They list required `.env` changes.

3. **Pull and restart.**

    ```bash
    git pull                               # compose files, scripts, docs
    # Pin a version (recommended) or use latest:
    #   WEIRLING_VERSION=v0.3.0 in .env (READPRISM_VERSION still works)
    docker compose pull
    docker compose up -d
    docker compose logs -f backend         # watch for "migrate: database is at head"
    ```

    The backend applies database migrations on start, under a lock, so it is
    safe with several containers. To run them yourself as a separate step, set
    `AUTO_MIGRATE=false` and run `docker compose exec backend python -m app.migrate`.

4. **Check.** `curl -s localhost:8000/health` should report `"status":"ok"`.
    Open the app, sign in, and load your digest.

## Rolling back

Restore the backup from step 1 and pin the previous version:

```bash
# WEIRLING_VERSION=<previous version> in .env
docker compose pull && docker compose up -d
./scripts/restore.sh /var/backups/readprism/readprism-<before-upgrade>.tar.gz
```

Prefer this over `alembic downgrade`: some migrations drop or reshape data
(see the notes), and a downgrade can't bring dropped data back. The backup
can.

## ReadPrism is now Weirling (v0.3.0)

The product is renamed (#340). Your data, sign-ins and settings carry over
unchanged; there is nothing to migrate.

!!! warning "Keep your install folder's name"
    Docker names your data volumes after the folder that holds
    `docker-compose.yml` (for example `readprism_postgres_data`). If you rename
    or re-clone into a folder called `weirling`, Compose starts with **empty**
    volumes. Keep the folder, or set `COMPOSE_PROJECT_NAME=readprism` in `.env`.

- **Images** are now `ghcr.io/mohitmishra786/weirling/weirling-backend`
  (and `-frontend`, `-aio`). Pull the new compose files with `git pull` to
  use them. The old `readprism-*` image names are no longer published.
- **`WEIRLING_VERSION`** pins the image version; `READPRISM_VERSION` is still
  read.
- **The repository** moves to `github.com/mohitmishra786/weirling`; GitHub
  redirects the old URL, and `git pull` keeps working.
- **Unchanged on purpose:** sign-in cookies and API tokens (`rp_…`), the
  database name and user (`readprism`), the Prometheus metric names
  (`readprism_*`) and dashboards, and backup archive names. Existing
  dashboards, alerts, backups and scripts keep working.
- The crawler now identifies as `Weirling/1.0 (+https://weirling.com/bot)`.

## v0.1.0 → v0.2.0

The first upgrade across many changes (migrations 0022 to 0037). Read all of
this before step 3.

**Required `.env` changes**

- **`SECRET_KEY` must be set and strong**, or the backend refuses to start.
  `APP_ENV` now defaults to `production`. Keep your existing `SECRET_KEY` if
  it is 32+ random characters (changing it signs everyone out and breaks old
  email links). Otherwise empty the value (`SECRET_KEY=`) and run
  `./scripts/init_env.sh`: it fills `SECRET_KEY`, `REFRESH_SECRET_KEY` and
  `METRICS_TOKEN` only where they are missing, empty or the old placeholder,
  and leaves everything else alone.
- **Registration is closed by default on self-host**: only the first account
  can sign up. Existing accounts keep working. To let others join, set
  `REGISTRATION_MODE=invite` (with `REGISTRATION_INVITE_CODES`) or `open`.
- **Sign-in moved to httpOnly cookies.** Everyone signs in once more after the
  upgrade. If the web app and the API are on different subdomains, set
  `COOKIE_DOMAIN=.example.com`. Over plain HTTP on a LAN, keep
  `COOKIE_SECURE=auto`.
- **LLM settings were renamed**: `GROQ_API_KEY` → `LLM_API_KEY`, and the
  model settings → `LLM_MODEL_PRIMARY` / `LLM_MODEL_FAST`. The old names still
  work for now and log a deprecation warning; they go away in v0.3.

**Database migrations (automatic)**

- **0025, shared feeds**: a feed several people follow is now polled once.
  The migration creates one `feeds` row per distinct feed URL and links
  subscriptions and stored items to it; your trust, tags and reading history
  are untouched, newsletters stay private. Preview it before upgrading:
  `docker compose exec backend python -m app.feeds_plan` (read-only).
- **0032 drops the Teams tables** (`teams`, `team_members`): the unused Teams
  feature was removed.
  If you used it, export anything you need **before** upgrading; the
  downgrade recreates empty tables only.
- The others only add columns or tables (email verification, billing state,
  newsletter unsubscribe info, push subscriptions, and so on).

**Services and files**

- **Meilisearch is gone**: search runs on Postgres. Remove a `meilisearch`
  service from any compose override you keep.
- **Redis now persists** (append-only file in the existing volume), so
  sign-in links and sessions survive restarts. Use `scripts/restore.sh`
  for restores: it handles the append-only file.
- **Logs are JSON by default** (`LOG_FORMAT=json`, no personal data). Set
  `LOG_FORMAT=text` for the old format.
- **Browser extension 0.3.0** no longer asks for every site. After updating
  it, open its options and save your server URL again to grant access.

**Afterwards**: the first ingest after migration 0025 polls each shared feed
once; a backlog of new items over the first hour is normal.

## Writing release notes

Each release gets `docs/releases/vX.Y.Z.md` from
[the template](releases/TEMPLATE.md), and its upgrade-relevant parts go into
this file.
