# ADR 0001 — Celery runs with `--pool=solo`

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

Do **not** simply remove `--pool=solo` to "add concurrency" — doing so
reintroduces the cross-loop bug. Address the engine-per-process concern first
(option 2) or use option 1.
