# ADR 0001: Celery runs with `--pool=solo`

- **Status:** Accepted
- **Date:** 2026-07-21
- **Context tags:** workers, async, scalability

## Context

The application is async end-to-end (SQLAlchemy async engine on asyncpg, async
services). Celery tasks wrap these async services with `asyncio.run(...)`.

Celery's default prefork pool forks worker processes and, combined with our
async engine, hit a **cross-event-loop bug**: an asyncpg connection created on
one event loop was reused from another, raising
`got Future attached to a different loop` errors (fixed in commit c12ca4b). The
mitigation that made the worker reliable was to run it single-process:

```
celery -A app.workers.celery_app worker --loglevel=info --pool=solo
```

`--pool=solo` executes one task at a time in a single process/loop, so no
connection ever crosses loops.

## Decision

Run the worker with `--pool=solo` for now. This is a **known, documented
scalability ceiling**, not a bug: ingestion, embedding, and digest tasks are
serialized on one worker container.

## Consequences

- A slow task (e.g. a 30s Playwright scrape) blocks everything queued behind it
  on that worker (head-of-line blocking).
- Throughput scales only by running more worker *containers*, not threads.
- It is correct and stable, which is the right trade-off pre-scale.

## Migration path (when this becomes the bottleneck)

Pick one, in rough order of effort:

1. **Split queues + one solo worker per queue** (audit 07-2). Route
   `scrape` / `embed` / `digest` to separate queues so a slow scrape can't
   starve digests. Cheapest win; keeps `--pool=solo` per container.
2. **Per-process event loop with prefork.** Ensure each forked worker creates
   its own async engine/connection lazily inside the worker process (e.g. via a
   `worker_process_init` signal that disposes/recreates the engine), so no
   connection is shared across processes. Then `--pool=prefork` becomes safe.
3. **Move to a dedicated async task runner** (e.g. `arq`/`taskiq`) that is
   loop-native, if Celery's model keeps fighting the async engine.

## Warning to future contributors

Do **not** simply remove `--pool=solo` to "add concurrency"; doing so
reintroduces the cross-loop bug. Address the engine-per-process concern first
(option 2) or use option 1.

## Update 2026-10-18: scaling for hosted (#239)

Option 1 is in place (`worker-scrape`, `worker-embed`, `worker-digest`).
Hosted capacity now scales **by process**: run more solo workers of the
queue that is behind, e.g.

```
docker compose up -d --scale worker-digest=4 --scale worker-embed=2
```

Each replica names itself `<queue>@<container hostname>`, and its healthcheck
pings that name. (Before this update the shared healthcheck pinged
`celery@<hostname>`, which no worker answers, so workers showed unhealthy.)
`task_acks_late` + `worker_prefetch_multiplier=1` keep a replica from holding
tasks another replica could run. Beat must stay a single instance.

**What to watch.** `GET /api/v1/metrics/queues` (metrics token) reports, per
hour window:

- `queue_wait_seconds` per queue (publish → start), p50/p95/max;
- `task_runtime_seconds` per task;
- `digest_delivery`: time from a scheduled digest falling due to its
  delivery task finishing, and the share within `DIGEST_ON_TIME_SECONDS`
  (default 900 s).

**Targets.** Digest on-time ≥ 99%. `digest` queue wait p95 < 60 s.
`embed` queue wait p95 < 10 min. Add a replica to the queue whose wait p95
breaches its target. Prefork (option 2) is still unnecessary while
process-level scale meets these targets.

**Load test.** `backend/scripts/load_test_digests.py` creates N synthetic
users on a running stack, queues their digests as the scheduler would, and
prints the on-time ratio from the endpoint above. The 1,000-user acceptance
run for #239 has to happen on the hosted environment; it has not been run
in development.
