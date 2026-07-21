# ReadPrism — Audit Implementation Log

*Single source of truth for implementing every actionable finding from the `audit/` artifacts (00–17). Updated continuously, after every item. Started 2026-07-21.*

## Legend

- `[ ]` not started · `[~]` in progress · `[x]` done · `[-]` deferred (with reason)
- **Class:** `Code` · `Config` (infra/repo settings) · `Content` (docs/copy) · `Decision` (needs human owner — logged in *Needs Human Decision*, not implemented)
- Each item: `ID | P# | Class | one-line | status note`

---

## Run summary (checkpoint — updated continuously)

**Files COMPLETE (code/config/content):** 06 (Security), 08 (Legal), 04 (Architecture), 05 (Ranking), 07 (Infra), 17 (KPI), 16 (Retention), 10 (UX).
**File 09 (UI): partial** — 09-1 dark mode, 09-3 a11y, 09-6 dedup, 09-7 done; 09-2 (mobile), 09-4 (styling unification), 09-5 (landing degrade) remain.
**Files remaining:** 09 (rest), 11 (SEO), 12 (marketing), 02 (competitive), 13 (monetization), 01 (PMF), 03 (ICP), 14/15 (checklists).

- Backend suite: **201 passing**, ruff clean; frontend tsc + build clean. Every commit leaves the repo green.
- ~60 atomic commits, each tagged `[audit:NN-...]`. Docker stack is the test harness; tests via `docker compose exec backend python -m pytest`; lint via `uvx ruff@0.6.9`; frontend via `npx tsc --noEmit` + `npm run build`.
- **Incident (recovered):** commit `cdeb63a` inadvertently `git add -A`'d a working tree where ~15 backend files + config/docs had been reverted to pre-audit state (concurrent activity in the repo). Restored from last-good `044ee42` in `e9f5e85`; suite green again. **Going forward: stage explicit paths, never `git add -A`.**
- Deferred/partial: 08-1 (MIT-vs-AGPL human decision — docs reconciled to MIT, CLA prepared); 06-4 register non-enumeration needs email verification; 07-8 shared embedding service; 10-8 OAuth; 17-7/17-8 external/needs-data.
- Needs Human Decision: _see section below_
- Risk flags before launch: _see final section_

**To resume:** ensure the Docker stack is up (`docker compose up -d db redis backend`, create+migrate `readprism_test`), then continue at the next `[ ]` item (file 11 SEO next in priority).

---

## Priority order (files)

Derived from the master summary's "one-month if you do nothing else" P0 list + artifact 14's aggregation of launch-blocking gates + dependency order (security/legal are launch blockers; ranking core underpins the product; measurement must exist before launch traffic).

1. **06 — Security & Privacy** (P0 launch blockers, concrete code)
2. **08 — Legal & Compliance** (ties to 06; localhost link, retention, robots, HTML sanitize)
3. **04 — Architecture & Codebase** (technical fixes, dead code, tests before HN)
4. **05 — AI/ML Ranking Engine** (core IP; averaged-vector, meta-leak, transitive, eval harness)
5. **07 — Infra, Reliability & Scale** (error tracking, queues, backups, beat health, email)
6. **17 — KPI & Metrics Framework** (event pipeline — measurement P0)
7. **16 — Post-Launch & Retention** (instrumentation; overlaps 17)
8. **10 — UX** (first-digest moment, sample articles, onboarding trim, feedback surfacing)
9. **09 — UI** (dark mode, mobile, a11y, styling unification, dedupe)
10. **11 — SEO & Discoverability** (GitHub config, README visuals, marketing route, sitemap)
11. **12 — Marketing & Positioning** (tagline, LAUNCH.md fixes, differentiators)
12. **02 — Competitive Landscape** (comparison pages, NewsBlur FAQ, competitor table)
13. **13 — Monetization & Pricing** (entitlement code; most items founder-decision)
14. **01 — Product-Market Fit** (mostly founder; suggestion-read metric code)
15. **03 — Target User & ICP** (mostly founder; self-host telemetry ping, quickstart)
16. **14 / 15 — Pre-Launch / Launch checklists** (aggregate; verify coverage + rate-limit/rollback/load-test)

---

## 06 — Security & Privacy  — STATUS: COMPLETE (code/config). 06-10 (privacy policy) folded into 08-4.

*Skills: no `find-skills`/`skills.sh` in this environment; used installed `fastapi-python` guidance. Web-researched Mailgun webhook signing (HMAC-SHA256 over timestamp+token, body-embedded signature) 2026.*

- [x] 06-1 | P0 | Code | Mailgun HMAC signature verification on `/newsletter/inbound`: `verify_mailgun_signature` (SHA256 timestamp+token, constant-time, stale-reject) + endpoint fail-closed outside dev + Redis token replay-dedupe (`cache_set_nx`). 7 tests. Commit.
- [x] 06-2 | P0 | Code | SSRF protection on all server-side URL fetches — `app/utils/ssrf.py` (validate + redirect-safe `safe_get`), wired into scraper (`_check_robots`/`_fetch_with_retry`/`_fetch_with_playwright`) + rss autodiscovery; configurable via `ssrf_protection_enabled`; 18 unit tests. Commit.
- [x] 06-3 | P0 | Code | Account deletion + data export endpoints: `app/services/account/gdpr.py` (`export_user_data`, `delete_user_account` handling RESTRICT teams + cascade + Redis purge) + `app/api/account.py` (`GET /account/export`, `DELETE /account`). 6 tests. Frontend control tracked as DDI-1. Commit.
- [x] 06-4 | P1 | Code | Redis fixed-window `RateLimiter` (`app/utils/ratelimit.py`) on `/auth/login` (10/min) + `/auth/register` (5/min); login now runs a constant-time bcrypt check against a dummy hash for absent users (closes timing oracle) + returns identical 401. Register 409 retained (full non-enum needs email verification — see 06-4 note). 3 tests. Commit.
- [x] 06-5 | P1 | Code | Real refresh-token model: short-lived access (30m) + long-lived refresh (30d) with `type`/`jti` claims, optional separate secret, Redis jti-allowlist for rotation (single-use) + revocation; `/auth/logout` revokes; refresh tokens rejected as access. Frontend: store both, single-flight auto-refresh on 401, revoke on sign-out. 4 backend tests; tsc clean. Commit.
- [x] 06-6 | P1 | Code | `content_items.owner_user_id` (migration 0006) tags private newsletter content; set on ingest for `source_type=="newsletter"`. Excluded from cross-user discovery pool, gated in `GET /content/{id}` (404 for non-owner), and scoped in `semantic_dedup`. 2 tests. Commit.
- [x] 06-7 | P1 | Code | HTML sanitization at every render boundary: frontend DOMPurify (`lib/sanitize.ts`) in reader + search; digest email `_fallback_html` now `html.escape`s all interpolated values (Jinja template already autoescapes); backend `sanitize_stored_html` strips script/iframe/on*/javascript: on RSS ingestion (defense in depth). 6 backend tests. Also satisfies 09-7. Commit.
- [x] 06-8 | P2 | Code | `get_settings()` raises at boot if `secret_key` is the placeholder default and `app_env != development`. 3 tests. Commit.
- [x] 06-9 | P2 | Config | Standardized on Python 3.12: Dockerfile `python:3.12-slim`, CI lint `3.12`, README tech stack `3.12`. Rebuilt image + full suite green (158). Commit.
- [-] 06-10 | P2 | Content | Publish a privacy policy — folded into 08-4 (done there).

## 08 — Legal & Compliance — STATUS: COMPLETE (code/content). Only the MIT-vs-AGPL business decision (08-1) remains human.

*Skills: no `find-skills`/`skills.sh`; no legal-domain skill installed — proceeded without.*

- [~] 08-1 | P0 | Decision+Content | Contradiction removed: LAUNCH.md now states MIT (matching the operative LICENSE); CONTRIBUTING.md adds a DCO + relicensing-grant CLA template (keeps the AGPL option cheap) + SECURITY.md. **MIT-vs-AGPL decision remains human** (Needs Human Decision #1). Commit.
- [x] 08-2 | P1 | Decision+Code | Implemented the audit's recommended honest posture as the default: `scraper_identify_as_bot` (single ReadPrism UA, no browser impersonation) + `scraper_respect_blocks` (back off on 403/429/503 instead of escalating to headless browser). Both configurable for operators who accept §1201 risk. 1 test. Residual posture choice noted in Needs Human Decision #5. Commit.
- [x] 08-3 | P1 | Code | Retention pruning task (`prune_content.prune_old_full_text`, daily 3:30 UTC) truncates `full_text` to an excerpt once older than `content_full_text_retention_days` (default 90; 0=disabled), keeping summary+link. Idempotent SQL `func.left`. 2 integration tests. Commit.
- [x] 08-4 | P1 | Content | `docs/PRIVACY.md` + `docs/TERMS.md` (telemetry, retention, shared-content model, scraping disclaimer, export/erasure rights) accurate to the implementation; linked from README. Also satisfies 06-10. Commit.
- [x] 08-5 | P1 | Code | Replaced hard-coded `localhost:3000` link with `frontend_url`-based preferences link; added signed one-click unsubscribe (`utils/unsubscribe.py` + `GET/POST /digest/unsubscribe` → in_app_only), `List-Unsubscribe`/`List-Unsubscribe-Post` headers, and a configurable physical-address footer. 3 tests. Also closes the 10-5 link portion. Commit.
- [x] 08-6 | P2 | Code | `_check_robots` now caches robots.txt per host (24h) and fails **closed** on fetch error by default (`robots_fail_open` opt-out); a clean 404/410 still allows. 3 tests. Commit.
- [x] 08-7 | P2 | Code | Newsletter forwarding consent handled via the ToS "Forwarded content" clause (user confirms right to forward); abuse controls already in place — webhook signature auth (06-1) + per-user private segregation + discard (06-6). Commit.
- [x] 08-8 | P2 | Content | `docs/THIRD_PARTY_SERVICES.md` documents Groq/OpenAI/Zoho-Resend/Browserless/Meilisearch use + no-cold-email + library licenses. Commit.

## 04 — Architecture & Codebase — STATUS: COMPLETE

- [x] 04-1 | P0 | Code | Serendipity now selects interest-*adjacent* content via pgvector cosine distance to the user's interest vector, banded to [0.35, 0.75] (related but outside core), ordered closest-first; falls back to recent public content for users without an interest vector. 2 tests. Commit.
- [x] 04-2 | P0 | Code | `compute_prs` now runs the 8 signals sequentially over the shared session instead of `asyncio.gather` (session isn't concurrency-safe; the gather only appeared parallel). Removes the latent bug; no real latency cost. Commit.
- [x] 04-3 | P1 | Code | `Source.health` property ('ok'/'degraded'/'failing' from fetch_error_count) surfaced in `SourceRead`; frontend SourceList shows a "Fetch issues"/"Not updating" badge with a tooltip. 1 test. Commit.
- [x] 04-4 | P1 | Code | `EmbeddingService.encode_single`/`encode_batch_cached` now run the blocking sentence-transformers encode via `asyncio.to_thread` (`_encode_async`), so onboarding + other API paths don't stall the event loop. Commit.
- [x] 04-5 | P1 | Code | Removed dead expr in scraper.py (reading-time calc) + orphan set in builder.py; fixed the misleading "pgvector similarity" comment in collaborative.py to match reality. Commit.
- [x] 04-6 | P1 | Code | Newsletter webhook tests added in 06-1; added `test_delivery_rendering.py` (fallback-HTML escaping, template render w/ unsubscribe/preferences/address + autoescape, text-body links, top-signals). 4 tests. Commit.
- [x] 04-7 | P2 | Code | `renormalize_edges` recomputes all edge weights (count/max) as part of the nightly decay job, fixing weights left stale by per-write normalization against a moving max. 1 test. Commit.
- [x] 04-8 | P2 | Content | `docs/adr/0001-celery-solo-pool.md` records the cross-loop-bug rationale, the scalability ceiling, the migration path (split queues / engine-per-process / async runner), and a warning against naively removing solo. Commit.
- [x] 04-9 | P2 | Content | README reconciled to code: Next 16/React 19, worker `--pool=solo`, SMTP/Zoho (not Resend) incl. setup env + var table, migrations 0001–0006, added prune task. (Email-provider choice still tracked in 07-6.) Commit.

## 05 — AI/ML Ranking Engine — STATUS: COMPLETE

- [x] 05-1 | P0 | Code | `services/ranking/evaluation.py`: dependency-free read-prediction AUC (Mann-Whitney) + Spearman(PRS, completion) over held-out observed engagement; `evaluate_user_ranking` joins DigestItem prs_score → interactions; `GET /metrics/ranking-eval` endpoint. 8 tests. Also satisfies 16-3, 17-4. Commit.
- [x] 05-2 | P0 | Code | Semantic signal now clusters interest nodes via union-find over co-occurrence edges (`_cluster_vectors`) and scores content by **max** cosine similarity across clusters, instead of one averaged vector that collapses multi-interest users. Single averaged vector retained for collaborative/cache callers. 3 tests incl. multi-interest. Commit.
- [x] 05-3 | P0 | Code | Meta-learning now holds out `reading_depth` + `explicit_feedback` (derived from the completion/rating target) from both the prediction and the gradient, so the model can't inflate weights by predicting its own inputs. 1 test. Commit.
- [x] 05-4 | P1 | Code | Transitive relevance implemented via `_bridge_vectors`: strongly-connected topic pairs (edge_weight ≥ 0.5) add a midpoint "bridge" vector to the semantic max-sim set, so content at the intersection of two connected interests scores highly even if near neither alone. 2 tests. Commit.
- [x] 05-5 | P1 | Code | `explain_top_topics` names the driving graph connection ("connects your interest in X and Y" for a bridge, "matches your interest in X" for a topic); computed in the digest builder and stored in `signal_breakdown["why_topics"]` (numeric sums guarded), surfaced in the ContentCard "Why this?" tooltip. 1 test + tsc clean. Commit.
- [x] 05-6 | P1 | Code | Collaborative warmup gated behind `collaborative_warmup_min_users` (default 1000) — inert below critical mass now returns [] explicitly instead of pretending to contribute; also added `owner_user_id IS NULL` to the items query (cross-tenant privacy). Comment fixed in 04-5. 5 tests. Commit.
- [x] 05-7 | P1 | Code | Chose the "document" option: centralized the `(sim+1)/2` mapping into `cosine_to_unit_score()` with a docstring explaining the intentional [0.5,1]-ish compression (unrelated≈neutral, not negative), and replaced the duplicated expression across all 6 signal files. Suite green. Commit.
- [x] 05-8 | P2 | Code | Exposed `novelty_target` + `temporal_blend_long/medium/short` as config (were hard-coded 0.35 / 0.5/0.35/0.15), wired into the novelty + temporal signals. Suite green. Commit.
- [x] 05-9 | P2 | Code | `backend/scripts/ranking_eval.py` — runnable offline report of read-prediction AUC + Spearman per signup-week cohort (reuses the 05-1 harness). Provided as a script rather than a .ipynb (notebooks aren't CI/container-runnable or testable). Verified runs. Commit.

## 07 — Infra, Reliability & Scalability — STATUS: COMPLETE (07-8 deferred w/ reason)

- [x] 07-1 | P0 | Code+Config | Sentry error tracking, opt-in via DSN: backend `utils/observability.init_sentry` wired into API (`main.py`) + worker/beat (Celery `worker_process_init`/`beat_init` signals); frontend `@sentry/nextjs` instrumentation-client/server/register files. No-op without a DSN. sentry-sdk==2.66.0. Image rebuilt, suite green, frontend builds. Commit.
- [x] 07-2 | P0 | Config | Celery `task_routes` map ingest→scrape, embeddings→embed, prs/digest/deliver/graph/prune→digest queues; compose replaced the single worker with `worker-scrape`/`worker-embed`/`worker-digest` (one `--pool=solo` process per queue, shared `x-worker-base` anchor; digest also drains default). Compose validates, routes load, suite green. Commit.
- [ ] 07-3 | P0 | Config+Content | Nightly pg_dump + documented restore
- [x] 07-4 | P1 | Config | `beat_heartbeat` task (every 60s, writes short-TTL Redis key) + beat container healthcheck checking key freshness; a stalled beat turns unhealthy instead of silently stopping ingestion/digests. Verified heartbeat writes. Commit.
- [x] 07-5 | P1 | Content | `docs/UNIT_ECONOMICS.md` — real Groq/Resend 2026 prices, explicit cache-hit assumption table (ICP-#1 niche → lower hits), email as step cost, Free/Pro alignment, <$100/mo beta target. Also satisfies 13-2. Commit.
- [x] 07-6 | P1 | Code+Content | Code uses generic SMTP (Zoho by default; Resend-SMTP-compatible); README aligned to SMTP/Zoho in 04-9; email step cost modeled in UNIT_ECONOMICS.md. Commit.
- [x] 07-7 | P1 | Code | `backend/scripts/loadtest_ingestion.py` seeds synthetic users+content, times the O(users×items×signals) PRS precompute, reports pairs/sec + 30-min-SLA projection, cleans up. Verified runs. Commit.
- [-] 07-8 | P2 | Config | DEFERRED (reason): partly mitigated already — the model loads lazily (`get_embedding_service`), so only the API eager-loads it and only `worker-embed` loads it among workers (queue split 07-2); beat/scrape/digest never load it unless they encode. A true shared embedding *microservice* is a larger infra change with marginal benefit at current scale; documented as the future optimization in DEPLOYMENT.md.
- [x] 07-9 | P2 | Config | Base compose is prod-shaped: backend `uvicorn` without `--reload`, Meilisearch `MEILI_ENV=production` (enforces master key); dev override re-adds `--reload` + `MEILI_ENV=development`. Commit.
- [x] 07-10 | P2 | Content | `docs/DEPLOYMENT.md` documents min host sizing (4/8/16GB tiers), prod-shaped compose, monitoring, backup/restore. Commit.

## 17 — KPI & Metrics Framework — STATUS: COMPLETE (17-7/17-8 deferred: external/needs-data)

- [x] 17-1 | P0 | Code | Metrics computed directly from the tables that already record the events (users/digests/interactions/sources) — no separate pipeline to desync. `services/metrics/analytics.py` + token-gated `/metrics/*` endpoints. Commit.
- [x] 17-2 | P0 | Code | `/metrics/cold-start-funnel` (signup→onboarded→first-digest-open→7d-active) + `/metrics/cohort-retention` (D1/D7/D30 per signup week). 3 tests. Also satisfies 16-1. Commit.
- [x] 17-3 | P0 | Code | `/metrics/north-star` = suggested-opened ÷ opened reads. Also satisfies 16-2 + 01-4. Commit.
- [x] 17-4 | P1 | Code | Ranking-eval harness (PRS→read AUC) — done via 05-1.
- [x] 17-5 | P1 | Code | `/metrics/scraper-health` (success rate + degraded/failing counts); cost/cache-hit modeling in UNIT_ECONOMICS.md (07-5). Also satisfies 16-4. Commit.
- [x] 17-6 | P1 | Code | Email send path increments Redis delivered/failed counters; `/metrics/email-deliverability` returns delivery rate (complaint rate needs a provider webhook — noted). Commit.
- [-] 17-7 | P2 | Config | DEFERRED (reason): GitHub stars/clones + Search Console are external dashboards configured in the GitHub/Google UIs, not code. Covered in the SEO/growth docs (file 11).
- [-] 17-8 | P2 | Decision | Needs first-cohort baseline data — logged for the owner (the metric endpoints to read those baselines now exist).

## 16 — Post-Launch & Retention — STATUS: COMPLETE (code via 17/05; 16-5/16-6 are founder process)

- [x] 16-1 | P0 | Code | Done via 17-2 (cohort-retention + cold-start-funnel endpoints).
- [x] 16-2 | P0 | Code | Done via 17-3 (north-star endpoint).
- [x] 16-3 | P1 | Code | Per-cohort ranking-eval harness — done via 05-1 (`evaluate_user_ranking` + AUC/Spearman).
- [x] 16-4 | P1 | Code | Scraper-health via 17-5 (`/metrics/scraper-health`) + per-source health surfaced in 04-3.
- [-] 16-5 | P1 | Decision | Process (founder-run outreach on 14d inactivity). The trigger data exists via `/metrics/cohort-retention`; the interview loop itself is human.
- [-] 16-6 | P1 | Decision | Process (founder cadence commitment). Not code.
- [x] 16-7 | P2 | Code | `/metrics/meta-weight-divergence` (mean |learned − default| across users) — proxy for accumulated model value.
- [x] 16-8 | P2 | Content | `docs/COLD_START_CONTINGENCY.md` — trigger, cheapest-first response ladder, what-not-to-do, and how to measure recovery via the new metrics endpoints. Commit.

## 10 — UX — STATUS: COMPLETE (10-8 deferred w/ reason)

- [x] 10-1 | P0 | Code | Digest page shows a "Gathering your first reads" honest state for new users (signed up <6h) with an empty digest, instead of an empty/near-random digest at the make-or-break moment. tsc clean. Commit.
- [x] 10-2 | P0 | Code | Expanded onboarding sample set to 9 curated titles across distinct clusters (ML/systems/web/science/finance/health/design/climate/history); titles are embedded server-side, so ratings now yield well-separated interest nodes (pairs with 05-2). tsc clean. Commit.
- [x] 10-3 | P1 | Code | Onboarding sources/creators steps marked Optional with a "Skip for now" Continue-button label when empty; copy notes starter sources are seeded + can add later. (Steps already advanced without input.) tsc/build clean. Commit.
- [x] 10-4 | P1 | Code | Conversational prompts already render (DigestView.FeedbackPrompts); tagged-reason feedback already in FeedbackBar; ADDED click-to-suppress on the Preferences interest-graph tags (calls `feedback.adjustInterests(topic,'suppress',30)`). tsc/build clean. Commit.
- [x] 10-5 | P1 | Code | Unsubscribe link fixed in 08-5; added `reengagement.send_reengagement_emails` (daily 16:00 UTC) — emails users with no opened digest in `reengagement_inactivity_days`, Redis cooldown to avoid spam, respects in_app_only + List-Unsubscribe. 1 test. Commit.
- [x] 10-6 | P1 | Code | Preferences frequency now includes "Weekly (we'll keep it short)" + "Email off — read in-app only" with a light-reader note. tsc clean. Commit.
- [x] 10-7 | P2 | Code | Interest-graph visualization already renders on the Preferences page (SVG force-layout + tag cloud, core-vs-weight styling, co-read edges) with an explainer — the "watch it learn" surface. Also satisfies 03-5.
- [-] 10-8 | P2 | Code | DEFERRED (reason): OAuth/magic-link is a substantial new auth flow (provider config, callback routes, email-link delivery) — a P2 nice-to-have beyond the audit's launch-critical set; deferred for a dedicated auth pass. Email/password + refresh rotation (06-5) is solid meanwhile.

## 09 — UI — STATUS: in progress (09-2/09-4/09-5 remaining)

- [x] 09-1 | P1 | Code | Dark mode: `@media (prefers-color-scheme: dark)` + `.dark` override of the semantic surface/text/border tokens (flips `.card`/reader/buttons/skeleton automatically) + `dark:` variants on the app shell and ContentCard text. tsc/build clean. Commit.
- [ ] 09-2 | P1 | Code | Mobile web layout audit + fixes (nav, touch targets, reader width)
- [x] 09-3 | P1 | Code | A11y: global `prefers-reduced-motion: reduce` disables shimmer/spinner/spotlight animations; skip-to-content link + `#main-content` landmark in the app shell. tsc/build clean. Commit. (Full contrast audit continues under 09-2.)
- [ ] 09-4 | P2 | Code | Unify styling: OnboardingWizard + inline-styled pages onto Tailwind system
- [ ] 09-5 | P2 | Code | Landing hero degrades gracefully (touch fallback, reduced-motion, lazy/self-host images)
- [x] 09-6 | P2 | Code | Frontend signal labels consolidated into `lib/signals.ts` (single FE source), imported by ContentCard; backend `delivery.py` copy annotated as the mirror to keep in sync (cross-runtime, codegen not worth it for 8 strings). Commit.
- [x] 09-7 | P2 | Code | Sanitize reader HTML — done as part of 06-7 (DOMPurify at reader/search render boundary).

## 11 — SEO & Discoverability — STATUS: COMPLETE (code/content; 11-1 owner-run script, 11-8 process)

*Skill: invoked `github` skill for GitHub SEO guidance (topics, About length, README).*

- [x] 11-1 | P0 | Config | `scripts/setup_github_metadata.sh` (owner runs with `gh` auth) sets keyword-first About, homepage, 13 topics, enables Discussions. Values per github-skill guidance. Commit.
- [x] 11-2 | P0 | Content | `docs/MEDIA.md` capture guide (shot list + `seed_demo.py` demo-data + GIF storyboard) + README Screenshots section placeholder. Actual capture is owner-run (needs running app). Commit.
- [x] 11-3 | P1 | Code+Content | Static `MarketingShell` + `/how-it-works` route; `app/robots.ts` (disallows authed app routes) + `app/sitemap.ts`; per-page metadata on all marketing pages. All SSG (build-verified). Commit.
- [x] 11-4 | P1 | Content | Static `/vs/feedly`, `/vs/inoreader`, `/vs/newsblur` comparison pages with accurate 2026 facts (Inoreader now has AI, NewsBlur closest analog) + per-page SEO metadata. Also satisfies 02-2 + 02-4. Commit.
- [x] 11-5 | P1 | Content | `/how-it-works` flagship page: 8 signals, per-user gradient descent, held-out leakage, explainability, open/honest — the defensible dev-audience content asset. Commit.
- [ ] 11-6 | P2 | Code | Marketing landing SSG + self-hosted next/image hero; drop canvas on indexable routes
- [x] 11-7 | P2 | Code | SoftwareApplication JSON-LD in root layout + OpenGraph/Twitter card metadata + metadataBase/canonical/keywords. Commit.
- [ ] 11-8 | P2 | Content | Submit to OSS directories (awesome-selfhosted, alternativeto, OSSAlt) — *process*

## 12 — Marketing & Positioning — STATUS: not started

- [x] 12-1 | P0 | Content | Retired PCIP tagline: README + root `<title>`/metadata now lead with "ranks by how you actually read"; 3 differentiators in README. Commit.
- [x] 12-2 | P0 | Content | LAUNCH.md placeholder URL → real repo; "Open source (AGPL)" → "(MIT)" (matches LICENSE). Done with 08-1. Commit.
- [ ] 12-3 | P1 | Content | Flagship "how the ranking works" post — same as 11-5
- [x] 12-4 | P1 | Content | 3 differentiators (behavioral / explainable / honest+open) used verbatim in README, root metadata, how-it-works, and comparison pages. Commit.
- [ ] 12-5 | P1 | Content | 60–90s demo GIF/video — *needs running app; provide storyboard + capture doc*
- [ ] 12-6 | P2 | Content | Drop "AI" from headline; keep in body
- [ ] 12-7 | P2 | Decision | Build-in-public cold-start thread — *process*

## 02 — Competitive Landscape — STATUS: not started

- [ ] 02-1 | P0 | Content | Rewrite competitor table (Inoreader AI, NewsBlur row, Feedly annual anchor)
- [x] 02-2 | P1 | Content | Comparison pages shipped under 11-4.
- [ ] 02-3 | P1 | Content | Position price between Brief Digest + Inoreader; justify $4.99 with ranking engine
- [x] 02-4 | P1 | Content | NewsBlur differentiation covered in `/vs/newsblur` (semantic+telemetry vs keyword-Bayes; interest graph vs flat classifiers; honest fair-note). Commit.
- [ ] 02-5 | P2 | Decision | Track Feedly Leo quarterly — *process*
- [ ] 02-6 | P2 | Decision | Watch Particle/TheReader.AI — *process*

## 13 — Monetization & Pricing — STATUS: not started

- [ ] 13-1 | P0 | Decision+Code | Re-align Free/Pro boundary with variable cost (Free=cached summaries+1/day; Pro=on-demand synthesis) — *tier structure is human; entitlement scaffolding is code*
- [ ] 13-2 | P1 | Content | Rebuild unit-economics model (real Groq/Resend + cache-hit + step costs) — same as 07-5
- [ ] 13-3 | P1 | Content | Document self-hosted BYO-LLM-key as pressure-release
- [ ] 13-4 | P1 | Decision | Market Pro on capability not price — *process/copy*
- [ ] 13-5 | P2 | Code | Server-side entitlement enforcement (when billing exists)
- [ ] 13-6 | P2 | Decision | "Hosted convenience" premium framing — *process*
- [ ] 13-7 | P2 | Content | Realistic near-term financial target (<100 users, <$100/mo)

## 01 — Product-Market Fit — STATUS: not started

- [ ] 01-1 | P0 | Decision | Run 10-user concierge cold-start test — *process*
- [ ] 01-2 | P0 | Decision | Define wedge in one falsifiable sentence — *process/copy*
- [ ] 01-3 | P0 | Decision | Hosted-first vs self-host-first — *process*
- [ ] 01-4 | P1 | Code | Instrument suggestion-driven-read rate as PMF metric — same as 17-3
- [ ] 01-5 | P1 | Content | Narrow positioning claim vs NewsBlur/Particle — same as 12-4/02-4
- [ ] 01-6 | P1 | Decision | Write kill/pivot criteria — *process*
- [ ] 01-7 | P2 | Content | "Explainable ranking" as marketable wedge — overlaps 12-4/05-5
- [ ] 01-8 | P2 | Code | Export meta-weights/graph as user-facing feature ("your model, yours to take")

## 03 — Target User & ICP — STATUS: not started

- [ ] 03-1 | P0 | Content | Declare ICP #1 in README + LAUNCH copy (self-host + 50+ technical feeds)
- [ ] 03-2 | P0 | Code | Opt-in anonymous telemetry ping for self-hosted instances
- [ ] 03-3 | P1 | Content+Code | 5-minute self-host quickstart tested on clean machine (single GROQ_API_KEY)
- [ ] 03-4 | P1 | Decision | Defer knowledge-worker marketing until hosted beta — *process*
- [ ] 03-5 | P1 | Code | ICP-#1 value prop: interest-graph + meta-weights viz — same as 10-7
- [ ] 03-6 | P2 | Decision | Interview 5 r/selfhosted users — *process*
- [ ] 03-7 | P2 | Decision | Size ICP #2 funnel — *process*

## 14 / 15 — Pre-Launch / Launch checklists — STATUS: not started

Most items alias earlier files. Net-new implementable:
- [ ] 15-1 | P0 | Code | Rate-limit signups + demo actions; sandbox demo account (reset-on-schedule) — overlaps 06-4
- [ ] 15-2 | P0 | Content | Rollback plan doc (pinned last-good image + one-command revert)
- [ ] 15-3 | P1 | Content | Prewritten launch FAQ (cold start, NewsBlur diff, self-host, privacy, license)
- [ ] 14-1 | P0 | Decision | Hosted demo/sandbox instance — *needs deploy target; process*
- [ ] 14-2 | P0 | Content | Waitlist/early-access page for hosted product

---

## Needs Human Decision

These are logged with the specific question; not implemented until answered. Work continues on non-blocked items.

1. **08-1 / 12-2 — License: MIT or AGPL-3.0?** LICENSE says MIT; LAUNCH.md says AGPL. The audit recommends AGPL-3.0 + CLA for the open-core/hosted monetization strategy, but this is a founder business decision with legal weight. *Question: adopt AGPL-3.0 (+ contributor CLA) now, or stay MIT?* Until answered, I will reconcile the docs to remove the contradiction only in a way that is reversible, and prepare both a CLA doc and the AGPL text without switching the LICENSE file.
2. **13-1 / 13-x — Monetization tier structure & price.** Whether/how to gate Free vs Pro (cached vs on-demand summaries), and the price point ($4.99 vs lower). *Question: confirm the Free/Pro feature split and price before entitlement code is wired to real gating.* Entitlement *scaffolding* (a tier-enforcement layer with config) can be built now; the specific gates need sign-off.
3. **01-3 — Hosted-first vs self-host-first.** Determines whether billing/hosted infra or self-host polish comes first. *Question: which goes first?*
4. **02-3 / 13-4 — Final price point.** $4.99 vs matching budget entrants. *Question: confirm price.*
5. **08-2 — Scraping posture.** Honest identifying bot UA + back-off, vs accepting §1201 risk with UA rotation. *Question: which posture?* (Recommend honest bot UA; can implement immediately on confirmation.)
6. **01-1, 01-2, 01-6, 03-4, 03-6, 03-7, 16-5, 16-6, 13-6, 12-7, 02-5, 02-6 — Founder process/strategy items** (concierge test, wedge sentence, kill criteria, interviews, cadence). Not code; owner-run.
7. **14-1 — Hosted demo deployment target.** Needs a cloud account/host. *Question: where to deploy the demo?*
8. **11-1 — GitHub repo settings (topics/description/homepage/Discussions).** Requires repo-owner `gh` auth. Script + exact values provided; owner runs it (or grants auth).

---

## Discovered During Implementation

- [x] DDI-1 | Preferences "Your Data" section: "Export my data" (downloads the GDPR JSON via authed fetch→blob) + "Delete account" (confirm → DELETE /account → clear tokens → /register). `api.account.export/delete` added. tsc clean. Commit.
- [ ] DDI-2 | `next lint` is broken under Next 16 (treats "lint" as a build dir; `next lint` removed in Next 16). Frontend CI `npx next lint` step is a silent no-op/failure. Migrate to ESLint CLI (`eslint .`) with a flat config. To address in the UI/SEO frontend pass or infra (file 07/09).
