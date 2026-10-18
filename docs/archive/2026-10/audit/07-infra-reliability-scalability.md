# 07 — Infra, Reliability & Scalability Audit

*Evidence: docker-compose.yml, Dockerfiles, CI workflows, worker code + web search on current infra/LLM pricing (July 2026).*

## Status Snapshot

- Single-host Docker Compose stack is coherent: db (pgvector/pg16), redis, backend, worker, beat, meilisearch, browserless, frontend — healthchecks on most, sensible `depends_on: service_healthy`.
- **Hard scaling ceiling by design:** Celery worker runs `--pool=solo` (one task at a time) to dodge the asyncpg cross-loop bug. One embedding/scrape/digest at a time per worker container. This is the dominant scalability fact.
- **No observability**: no Sentry/error tracking, no metrics/Prometheus, no structured-log aggregation, no uptime monitoring. Logging is stdlib to stdout.
- **No backup/DR story**: named Docker volumes only; no pg_dump cron, no restore doc, no volume snapshot guidance.
- Not Kubernetes-ready (single-tenant compose, host-mounted volumes, `--reload` dev command in the committed compose backend service).
- **Unit-economics table in the spec does not survive current pricing** — the summary-cache assumption saves it partially, but the per-user LLM number is optimistic (details below).

## Reliability findings

- **beat has no healthcheck**; a silently dead beat scheduler stops all ingestion/digests with no signal. Worker healthcheck exists but `start_period: 90s` (model load).
- **Solo pool + long tasks = head-of-line blocking.** A slow Playwright scrape (30s timeout) blocks embeddings and digest builds queued behind it on the same worker. At any real source count, ingestion falls behind the 30-min schedule. Mitigation: separate Celery queues (scrape / embed / digest) and one worker container per queue.
- **Browserless MAX_CONCURRENT_SESSIONS=5** but backend `SCRAPER_MAX_CONCURRENCY=5` and worker is solo → effective scrape concurrency is 1. The pool is oversized for the worker model, or the worker model is undersized for the pool.
- **No retry/dead-letter on Celery tasks** beyond the scraper's internal httpx retry. A task raising mid-digest just logs and drops.
- `docker-compose.yml` backend command is `uvicorn --reload` (dev) — production compose should not hot-reload; override file is for dev.
- Meilisearch runs `MEILI_ENV=development` (no master-key enforcement in dev mode) in the base compose — search is effectively open.

## Scalability findings

- **PRS precompute** runs every 2h for "active users" and writes `prs_score` per (user, item). This is O(users × recent_items × 8 signals), each signal firing pgvector kNN queries. On solo workers this is the first thing to fall over as users grow. HNSW indexes help per-query; the multiplication doesn't.
- **Embeddings on CPU** (`EMBEDDING_DEVICE=cpu`, all-MiniLM-L6-v2). Fine for modest volume; the model load is ~60–90s per container start (three containers load it: backend, worker, beat all import embedding service). Consider a single embedding service, not per-container.
- **Interest-vector cache** is 1h TTL keyed per user, invalidated on reinforcement — reasonable.

## Unit-economics reality check (spec vs July 2026 pricing)

Spec claims **$0.31/mo free user, $0.95/mo Pro**, 81% Pro margin, profitability at ~8,000 Pro subs.

- **LLM summarization** (spec: $0.12 free / $0.48 Pro). Groq Llama 3.3 70B is **$0.59/M input, $0.79/M output** ([Groq pricing](https://groq.com/pricing)); batch API halves it, prompt caching helps. **Summary caching across all users of a shared source is the load-bearing assumption** and it *is* implemented (`summarization_cached`, shared `content_items`). With caching, a Pro user reading mostly popular sources could plausibly hit ~$0.20–0.50/mo. Without high cache-hit rates (niche sources, ICP #1's whole point), it's higher. **Verdict: plausible only if cache-hit rate is high — which contradicts the niche-reader ICP.**
- **Email** (spec: $0.02 free / $0.05 Pro). Resend free = 3,000/mo, 100/day; Pro $20/mo for 50k ([Resend pricing](https://resend.com/pricing)). One daily digest/user → 100/day free cap is hit at ~100 users; then $20/mo fixed covers ~50k sends = ~1,600 daily-digest users. So email is a **step cost**, not the linear $0.02/user the table implies. Also: **README says Resend, code uses Zoho SMTP** — Zoho has send limits (and isn't built for scale); pick one and model it.
- **Embeddings** "no API cost" — true, but CPU compute time isn't free at scale (it's the worker bottleneck, not a line item).
- **The 8,000-Pro path** implies ~$40k/mo revenue vs ~$8k infra. Given step costs (email tiers, worker sharding, managed Postgres) and the solo-pool ceiling, infra at 8k paying (plus their free cohort) is likely well above $8k. Treat the table as directionally-hopeful, not a plan.

## Checklist

- [ ] P0 | Add error tracking (Sentry or GlitchTip self-hosted) to backend + worker + frontend | You currently cannot know when digests silently fail | no observability in repo | S | eng
- [ ] P0 | Split Celery into scrape/embed/digest queues with a worker per queue (removes head-of-line blocking; unblocks off-solo path later) | Solo pool + mixed long tasks = ingestion falls behind at low source counts | docker-compose.yml worker | M | eng
- [ ] P0 | Add a backup story: nightly pg_dump + documented restore | Behavioral history is the whole product; one volume loss = total loss | volumes only in compose | S | eng
- [ ] P1 | Add a beat healthcheck / liveness alert | Dead beat = silent full stop of ingestion & digests | compose beat service | S | eng
- [ ] P1 | Re-model unit economics with real Groq/Resend numbers and an assumed cache-hit rate; separate step costs from per-user | Spec's table won't survive an HN cost thread | this artifact; spec §Unit Economics | M | founder |
- [ ] P1 | Pick one email provider (Resend *or* Zoho) and align README+code+costs | Doc/code contradiction + Zoho won't scale to digest volume | README vs `utils/email.py` | S | eng
- [ ] P1 | Load-test the ingestion + precompute path at 100 sources / 50 users on one host before launch | Validate the 30-min ingestion SLA holds under solo pool | none | M | eng
- [ ] P2 | Single shared embedding service instead of loading the model in 3 containers | ~60–90s×3 startup + RAM triplication | lifespan + worker + beat all import it | M | eng
- [ ] P2 | Remove `--reload` from base compose; enforce Meilisearch master key outside dev | Prod-shaped defaults | compose backend/meilisearch | S | eng
- [ ] P2 | Document minimum host sizing (RAM for model + pgvector + browserless) | README says 4GB; validate under load | README prerequisites | S | founder

## Top 5 if you only do 5 things

1. Add Sentry-class error tracking across all three runtimes.
2. Split Celery queues so scraping can't starve digests/embeddings.
3. Nightly pg_dump + a tested restore doc.
4. Re-model unit economics honestly (Groq $0.59/$0.79/M, Resend step costs, cache-hit assumption).
5. Add a beat liveness alert and load-test the ingestion SLA once.

**Revisit trigger:** re-run when moving off `--pool=solo`, before hosted launch, and at 500 active users.
