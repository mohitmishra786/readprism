# 04 — Architecture & Codebase Audit

*Evidence: direct code review of github.com/mohitmishra786/readprism@main (db91697 + bot bumps), July 2026.*

## Status Snapshot

- Genuinely well-structured for a solo project: clean domain-oriented `services/` (ingestion, ranking, interest_graph, digest, summarization, creator, cold_start, teams), thin API routers, SQLAlchemy 2.0 async throughout, Alembic migrations 0001–0005, HNSW pgvector indexes present in 0001.
- Test suite is real: 27 test files covering ranking signals, meta-weights, decay, digest sections, scraper, resolver; CI runs them against real Postgres+pgvector and is green.
- Async correctness is mostly right, with one big architectural concession: Celery runs `--pool=solo` (single task at a time) to avoid asyncpg cross-event-loop bugs — a real scalability ceiling honestly documented in docker-compose comments.
- There are LLM-generation fingerprints: dead expressions (`max(1, round(word_count / 238))` discarded in `scraper.py`; orphan set-comprehension in `builder.py:54`), and comments describing behavior the code doesn't do (collaborative warmup "via pgvector similarity" — actually a plain LIMIT 200 query + Redis cache reads).
- "Graceful degradation" (spec promise) is **partially implemented**: no-LLM mode works by design (`llm_configured`, keyword fallback, CI tests run with empty GROQ key), scraper has httpx→Playwright fallback with retry/backoff, signals fall back to 0.5 neutral. But source-failure *user notification* (spec: "degrade gracefully **with user notification**") is not implemented — `fetch_error_count` exists on sources; nothing surfaces it to users.

## Detailed findings

**Separation of concerns — good.** Routers stay thin; ranking math lives in services; workers wrap services. `scorer.py` composes signals via a clean `SIGNAL_MODULES` registry; adding a signal is one file + one dict entry.

**Async correctness.**
- `get_db` commits-on-success pattern is fine; `expire_on_commit=False` correct for async.
- Signals run via `asyncio.gather` sharing one `AsyncSession` — concurrent queries on a single session is *not safe* in SQLAlchemy async (session is not concurrency-safe). In practice each signal's awaits serialize on the session, so it works but the "parallel" claim is illusory; under future refactors this is a latent bug. Evidence: `scorer.py::compute_prs` gathers 8 coroutines all holding `session`.
- Blocking calls handled correctly where checked: SMTP via `asyncio.to_thread`; sentence-transformers `encode` is called synchronously inside async paths (`encode_batch_cached`) — **this blocks the event loop** during embedding computation. Acceptable in the solo Celery worker; a real problem if called from API request paths (onboarding does: `process_onboarding` → `encode_batch_cached`).
- Celery tasks wrap async services (cross-loop bug was hit and patched — commit c12ca4b "Celery cross-loop bug"); `--pool=solo` is the mitigation, not a fix.

**Schema sanity — good with nits.**
- pgvector: `Vector(384)` on content + interest nodes, HNSW indexes created in 0001 (`migrations/versions/0001_initial_schema.py:216-219`). Correct ops class (cosine).
- `content_items.url` globally unique → content is shared across users (good for summary-cache economics; a privacy trade-off flagged in artifact 06).
- `user_content_interactions` has a proper unique (user, content) constraint; telemetry columns added in 0003 mirror the frontend hook.
- Nit: `InterestEdge` is directed in schema but canonical-ordered in code (undirected in practice) — fine, but document it; "directed weighted graph" in the spec is already not what's built.
- Nit: edge normalization does a per-reinforcement `MAX(co_occurrence_count)` query and only renormalizes the *touched* edge — other edges' weights go stale relative to a moving max. Harmless now; wrong at scale.

**Test coverage vs claims.** Ranking logic, decay, sections, scraper fallback, resolver: covered. **Not covered:** digest delivery/email rendering, newsletter webhook, auth refresh flow, worker tasks end-to-end, anything requiring a live LLM (CI runs keyless). Frontend has zero tests (typecheck+build only). The commit-message claim "120 passed" is plausible given file count; treat LLM-path behavior as untested.

**Spec-vs-code gaps (carry-through):** per-user recency decay curve — absent; interest-transition detection — absent; serendipity selection = recent items from other users' sources + bottom-15% marking (diverges from spec's "interest-adjacent outside clusters"); digest length auto-learning — present (`builder.py::_adjust_digest_preferences`); feedback prompts — present.

## Checklist

- [ ] P0 | Fix serendipity selection to match intent: candidates should be interest-*adjacent* (embedding near cluster edges), not merely "recent items from other users' sources" | Current discovery section is effectively random-recent — it will feel dumb and poison the purest signal | `digest/builder.py:53-65`, `ranking/engine.py:78-84` | M | eng
- [ ] P0 | Stop sharing one AsyncSession across gathered signal coroutines (pass a session factory or serialize explicitly) | Latent concurrency bug in the hottest path | `scorer.py::compute_prs` | M | eng
- [ ] P1 | Surface source failure state to users (spec's "with user notification") | `fetch_error_count` accumulates invisibly; dead sources = silently degrading digests | models/source.py; no UI/API usage found | M | eng
- [ ] P1 | Move embedding encode calls off the event loop (`asyncio.to_thread` or dedicated worker queue) in API-triggered paths | Onboarding latency + event-loop stalls under concurrent signups | `utils/embeddings.py::encode_batch_cached`; `cold_start/onboarding.py` | M | eng
- [ ] P1 | Delete dead expressions & fix comment-code mismatches (scraper reading-time, builder orphan set, collaborative "pgvector" comment) | Reviewer trust; these will be called out publicly on HN | `scraper.py:~178`, `builder.py:54`, `collaborative.py:30-46` | S | eng
- [ ] P1 | Add tests for digest delivery rendering and the newsletter webhook (both currently untested & both user-facing) | Highest-blast-radius untested surfaces | tests/ tree | M | eng
- [ ] P2 | Renormalize edge weights in the decay job rather than per-write | Correctness at scale; cheap to do nightly | `graph.py::reinforce_edge` | S | eng
- [ ] P2 | Record an ADR for `--pool=solo` and the target migration path (per-process loop or worker sharding) | Future contributors will "fix" it and reintroduce the cross-loop bug | docker-compose.yml comments | S | eng
- [ ] P2 | Reconcile README (Next 14/React 18, Resend, worker "4 concurrency") with code (Next 16/React 19, Zoho SMTP, solo pool) | Docs drift measurable in 5 places already | README vs package.json/config.py/compose | S | founder

## Top 5 if you only do 5 things

1. Fix serendipity candidate selection — it's the core loop's weakest implemented link.
2. Fix the shared-session gather in `compute_prs`.
3. Surface source-fetch failures to users.
4. Add delivery + webhook tests.
5. Purge dead code / wrong comments before the HN audience reads the repo.

**Revisit trigger:** re-audit when Celery moves off `--pool=solo`, or before the hosted beta.
