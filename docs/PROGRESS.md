# ReadPrism — PROGRESS TRACKER (source of truth for work status)

> **Copy this file to `docs/PROGRESS.md` in the repo.** The implementing agent reads it at the start of every session and updates it after every task. If this file and your memory disagree, this file wins.
> Companion docs: `docs/ROADMAP.md` (why/what), `spec/PCIP_Proposal_V2.md` (product spec), `docs/adr/` (decision records).

Last updated: 2026-09-24, session 2
Current phase: **Phase 1 — Ingestion**
Last commit on `main`: `a485e45` (Phase 0 merged, then Dependabot #54 and #53)
Last commit on `main` when this file was seeded: `37b7f16`

---

## 1. How to use this file (protocol)

**Status tags** (edit the tag in place, keep the rest of the line):
`[TODO]` not started · `[DOING]` in progress (max 2 at a time) · `[DONE]` finished + evidence recorded · `[EXISTS]` audit found it already implemented and verified (still may need tests) · `[PARTIAL]` exists but incomplete (say what is missing in Evidence) · `[BLOCKED]` needs a human decision or external thing (say what in Evidence) · `[DROPPED]` intentionally not doing (say why)

**Rules**
1. A task is `[DONE]` only when: code merged to the working branch, tests added/updated and **green**, lint/type checks pass, docs updated, and the **Evidence** field names commit SHA + test names/commands + file paths. "Looks right" is not evidence.
2. One task = one or more atomic commits, message prefix `[TASK-ID]`, e.g. `[IN-01] Add conditional GET to feed fetcher`.
3. Never delete or weaken a test/lint/type rule to make something pass. If a check is wrong, fix it in a separate commit with an explanation in the Decision Log.
4. Do not start Phase N+1 tasks until the Phase N **Exit Gate** (section 5) is fully checked and recorded. P0-priority tasks in later phases may be pulled forward only if you log why.
5. Product decisions that are not already in the Decision Log → add to **Open Questions**, choose the safest reversible default, mark the task `[BLOCKED]` only if no safe default exists.
6. Append to the **Session Log** at the end of every session (or when context is nearly full). Newest entry on top.
7. Discoveries (bugs, surprises, spec conflicts) go in **Discoveries**, not buried in commit messages.

**Priority:** P0 must-fix/blocking · P1 core value · P2 valuable · P3 nice-to-have. **Size:** S ≤ half a day · M ≈ 1–2 days · L ≈ 3–5 days · XL > 1 week (split it).

---

## 2. Decision Log (binding unless superseded; add new rows, never edit old ones)

| ID | Decision | Rationale (short) | Date |
|----|----------|-------------------|------|
| D-01 | LLM access goes through one provider-agnostic client (OpenAI-compatible `base_url` + `model` env vars). No model ID is hard-coded. Default on Groq: `openai/gpt-oss-120b` (primary), `openai/gpt-oss-20b` (fast). | Groq shut down `llama-3.3-70b-versatile` and `llama-3.1-8b-instant` for free/developer tiers on 2026-08-16. Model churn will recur. | 2026-09-24 |
| D-02 | The digest must **never** fail or block because an LLM is unavailable. Fallback = extractive summary (lead sentences / TextRank). | Reliability > polish. Free-tier rate limits (TPM) are the binding constraint. | 2026-09-24 |
| D-03 | Default embedding model moves from `all-MiniLM-L6-v2` (≈256-token limit) to `nomic-embed-text-v1.5` (8k ctx, 768-d, uses `search_document:`/`search_query:` prefixes), **after** it wins on the golden retrieval check (IQ-02). MiniLM stays as `lite` profile. `bge-m3` is the multilingual option. | MiniLM only "sees" the first ~200 words of long-form articles. | 2026-09-24 |
| D-04 | Ranking = 3 stages: candidate generation → linear scoring over the 8 signals (per-user weights, learned online with shrinkage to a prior) → re-rank (MMR + cluster cap + novelty slots). All 8 features are **pre-consumption** (computable before the user sees the item). | Keeps the spec's formula and explainability (exact w·s contributions) while fixing leakage and diversity. | 2026-09-24 |
| D-05 | User interest = **multiple** cluster medoids (PinnerSage-style), not one mean vector. The interest graph remains the explainable layer on top. | A mean vector dilutes multi-topic users. | 2026-09-24 |
| D-06 | Cold start cannot rely on other users in a self-hosted instance. Use shipped topic priors + starter packs + imports + LLM interest expansion. Collaborative warmup stays behind `COLLAB_WARMUP` and is a safe no-op below N users. | Spec's Mechanism Two needs a population. | 2026-09-24 |
| D-07 | No third-party telemetry, ever. Anything that leaves the box (LLM calls, email provider, RSSHub bridge) is documented in the privacy doc. | Reading behavior is sensitive; trust is the product. | 2026-09-24 |
| D-08 | No paywall circumvention. Detect + label paywalled items. Respect robots.txt in scraping mode (not for explicitly user-supplied RSS URLs). Identify with an honest User-Agent. | Legal/ethical + sustainability. | 2026-09-24 |
| D-09 | Keep the service count low. Search = Postgres FTS + pgvector hybrid first; Meilisearch only if FTS proves insufficient (revisit at UX-11 gate). Offer a `lite` compose profile (no Browserless, MiniLM). | Self-hosters pay in RAM/ops; current stack is already 7 services / 4 GB. | 2026-09-24 |
| D-10 | Positioning: **developers who self-host and follow many technical feeds**. Hosted tiers, billing and team features are deferred until there is real pull (RL-09, EC-09 are backlog-only). | Niche-first; Artifact shows mass-market personalized news is a hard standalone business. | 2026-09-24 |
| D-11 | Platform coverage strategy: native feed recipes first, then an optional RSSHub bridge (`RSSHUB_BASE_URL`), then scraping. X/Twitter and LinkedIn remain honestly "unsupported". | RSSHub is a large maintained route network; avoid rebuilding connectors. | 2026-09-24 |
| D-12 | License and README drift must be resolved to whatever the `LICENSE` file says; do not change the license without the owner (see OQ-01). | Avoid accidental relicensing. | 2026-09-24 |

_(Agent appends new decisions below; ADR file for anything architectural.)_

---

## 3. Open Questions (needs the owner; state your assumed default)

| ID | Question | Assumed default until answered | Status |
|----|----------|-------------------------------|--------|
| OQ-01 | README (snapshot) says MIT, repo metadata says AGPL-3.0. Which is intended? | Keep whatever `LICENSE` file contains; fix README to match. | open |
| OQ-02 | Is a hosted offering planned in the next 6 months? | No — self-host only (D-10). | open |
| OQ-03 | Preferred default LLM provider for out-of-box setup (Groq free tier vs local Ollama vs OpenRouter)? | Groq (existing env vars), with Ollama documented. | open |
| OQ-04 | Is the existing `extension/` intended to be MV3 Chrome+Firefox? | Audit first (P0-04), then decide at EC-02. | open |

---

## 4. Task Backlog

### PHASE 0 — Audit & Stabilize  _(goal: know the truth, stop the bleeding)_

- **P0-01** [DONE] (P0·S) Bootstrap docs: add `docs/ROADMAP.md`, `docs/PROGRESS.md` (this file), `docs/adr/0000-template.md`. — Accept: files committed; README links to them. — Evidence: `28f9b42`. README links PROGRESS, ROADMAP, ARCHITECTURE, and the addendum.
- **P0-02** [PARTIAL] (P0·S) Clean-clone baseline. — Evidence: Docker Desktop was down at session start; `open -a Docker` brought it up. `docker compose up -d db redis` reused existing images and was healthy. Idle RAM: db 78 MiB, redis 20 MiB (host 7.6 GiB). `alembic heads` was `0006` before this branch; `alembic upgrade head` on this branch applied `0007`. `docker compose build backend` completed (image `readprism-backend:latest`, id `8506d6c8122c`); the build downloaded a 454 MB torch wheel because sentence-transformers pulls CUDA packages on linux/arm. Frontend image was not built and the UI was not clicked: no browser tool is connected, and the API was not left serving. Register and onboarding are covered by `tests/test_api/test_auth.py` and `tests/test_api/test_onboarding.py` (232 passed after the phase commits). Coverage % was not measured; pytest-cov is not installed.
- **P0-03** [DONE] (P0·S) Quality baseline, recorded before the phase-0 edits. — Evidence: `pytest tests/ -q` on image `a7a14463dcff` with the then-current source: **205 passed**, 6 warnings, 11.72s. `ruff check` and `ruff format --check`: clean (158 files). `mypy app --python-version 3.11 --ignore-missing-imports`: **14 errors in 8 files** (fixed in `2e93706`; re-run is clean, 113 files). Frontend `npx tsc --noEmit`: exit 0. `npm run build`: exit 0, Next.js reported **16.2.11** while `package.json` pins **16.2.12** (20 routes). `npm run lint` (`next lint`): exit 1, "Invalid project directory .../frontend/lint" — Next.js 16 removed `next lint`. No coverage number.
- **P0-04** [DONE] (P0·L) Feature audit. Matrix below has no `UNVERIFIED` row. — Evidence: file paths in section 6, read this session. Re-prioritization is in Discoveries (no new task ids; the existing IQ/IN items already cover the gaps).
- **P0-05** [DONE] (P0·M) LLM client. — Evidence: `6c68dd9`. Tests: `test_model_not_found_opens_circuit_and_stops`, `test_429_retries_then_succeeds`, `test_timeout_returns_none`, `test_digest_summary_ships_with_llm_unset`, `test_retired_groq_model_is_rewritten`. `llama-3.3-70b-versatile` and `llama-3.1-8b-instant` appear only in the retirement map (`config.py`) and that test. Call sites read `settings.llm_model_primary` / `llm_model_fast`.
- **P0-06** [DONE] (P0·M) `safe_fetch`. — Evidence: `17f0d03`. Tests in `test_ssrf.py` cover loopback, metadata, `10/8`, `[::1]`, mixed DNS answers, redirect to `127.0.0.1` (private hop not contacted), credentials, decimal loopback, body cap. `feedparser.parse` is only called with bytes (`rss_parser.py`). Residual: Browserless does its own DNS after the route hook; Meilisearch, Notion, Readwise, and the iTunes API host are operator URLs. ADR 0003.
- **P0-07** [DONE] (P0·M) HTML allowlist. — Evidence: `95dd760`. `nh3==0.3.7`. `test_xss_payloads_do_not_survive` and `test_email_template_escapes_item_html`. DOMPurify hook sets `rel=noopener noreferrer`. CSP on `/read/:path*` in `frontend/next.config.mjs`.
- **P0-08** [DONE] (P0·S) XML safety. — Evidence: same commit `95dd760` (landed with the sanitizer). `test_xxe_rejected`, `test_billion_laughs_rejected`, `test_parse_feed_rejects_entity_expansion`. Limits: `XML_MAX_BYTES`, `OPML_MAX_OUTLINES`.
- **P0-09** [DONE] (P0·M) Auth and config. — Evidence: bcrypt, refresh rotation, and login/register limits already existed and stayed green (`test_auth.py`, `test_ratelimit.py`). This branch adds the short-key refusal (`test_short_secret_key_fails_outside_development`), feedback rate limit, and production CORS limited to `FRONTEND_URL` + `CORS_EXTRA_ORIGINS` (`2e93706`). Model write-up: `docs/security.md`. Argon2id was not added; bcrypt is the hasher and D-09's "argon2id/bcrypt" is satisfied by bcrypt.
- **P0-10** [DONE] (P1·S) README matches LICENSE (AGPL-3.0), Next.js 16 / React 19, and the LLM settings. `docs/ARCHITECTURE.md` describes the code. — Evidence: `28f9b42`.
- **P0-11** [DONE] (P1·M) CI. — Evidence: on `main`, Backend run [35929735469](https://github.com/mohitmishra786/readprism/actions/runs/35929735469) for the Phase 0 merge succeeded (ruff, mypy, pytest, alembic head). Frontend and CodeQL succeeded for the follow-up Next 16.3.6 and fast-uri merges. `npm run lint` still calls removed `next lint` and is not a CI step.
- **P0-12** [DONE] (P2·S) Dependabot. — Evidence: owner merged #54 (`37ac752`, fast-uri 3.1.8) and #53 (`a485e45`, next 16.3.6). Both CI runs on `main` succeeded. Dependabot grouping was already in `.github/dependabot.yml`. `package.json` now pins `next` 16.3.6.
- **P0-13** [DONE] (P1·S) Addendum. — Evidence: `spec/PCIP_Proposal_V2_addendum.md` in `28f9b42`. Competitor prices stay in `docs/ROADMAP.md` §4 and are marked unverified there.

### PHASE 1 — Ingestion hardening  _(goal: never miss, never garbage)_

- **IN-01** [DONE] (P1·S) Fetch etiquette: conditional GET (store ETag/Last-Modified per feed, honor 304), gzip/br, honest UA with project URL. — Accept: second fetch of unchanged fixture server returns 304 and skips parse; test with local mock server. — Deps: P0-06 — Evidence: `fetch_feed` sends `If-None-Match` / `If-Modified-Since` and `Accept-Encoding: gzip, deflate, br` with UA `ReadPrism/1.0 (+https://readprism.app/bot)`. Columns `sources.http_etag` and `sources.http_last_modified` (migration 0008). Test `test_second_fetch_of_unchanged_feed_is_304_and_skips_parse` uses an httpx mock transport: first response 200, second 304, `feedparser.parse` called once. Dispatcher stores the validators. pytest 237 passed.
- **IN-02** [DONE] (P1·M) Adaptive polling scheduler: interval = clamp(median inter-item gap / 2, 15 min, 24 h) ±10% jitter; 304 ⇒ ×1.25 (cap 24 h); new items ⇒ ÷1.5 (floor 15 min); errors ⇒ exponential backoff (5 min·2ⁿ, cap 24 h); honor `Retry-After`/429; 410 ⇒ disable; permanent 301 ⇒ rewrite URL; per-host concurrency + politeness delay. — Accept: simulated-clock tests for each rule. — Deps: IN-01 — Evidence: `app/services/ingestion/schedule.py`, `tests/test_ingestion/test_schedule.py` (quiet growth, 24h cap, shrink + 20-gap window, error backoff, Retry-After, 410/7-day dead, 301 rewrite, 1s host gap). Migration 0009. Ingest skips sources whose `next_poll_at` is in the future and writes the next run. 301 rewrite helper is tested; the fetcher does not yet record a 301 hop separately from the final URL (safe_fetch follows it). That wiring stays for a follow-up inside IN-02 if a feed reports 301 without a usable final response.
- **IN-03** [DONE] (P1·M) Feed health model + UI: `healthy/degraded/failing/dead`, last success/error, items per week; visible on Sources page; one-time notice (digest footer) when a source turns dead. — Accept: e2e test flips a mock feed to 500 and observes status transitions + notice. — Deps: IN-02 — Evidence: `feed_status` is the API `health`. Sources page shows the label, last success, last error, and items in the last 7 days. A transition to dead sets `dead_notice_pending`; the digest footer names those sources once and then clears the flag. Tests: `test_repeated_500_then_410_marks_dead_and_queues_one_notice`, `test_dead_notice_is_rendered_once`, `test_source_health_surfaced`. Migration 0010.
- **IN-04** [DONE] (P1·M) Feed autodiscovery cascade: `<link rel=alternate>` → well-known paths (`/feed`, `/rss`, `/atom.xml`, `/index.xml`, `/feeds/posts/default`) → platform recipes → RSSHub → scrape mode; return ranked candidates. — Accept: ≥ 20 fixture sites (WordPress, Ghost, Substack, Blogger, Hugo, Jekyll, Medium pub, JS-only) resolved correctly. — Deps: P0-06 — Evidence: `app/services/ingestion/discover.py`. `test_fixture_site_resolves` covers 20 shapes (WordPress, WordPress.com, Ghost, href-before-type, Substack, custom-domain link, Blogger, Hugo link, Jekyll link, Medium user, Medium publication, Medium subdomain, YouTube channel id, Reddit, GitHub releases, arXiv, Hugo `/index.xml` probe, Jekyll `/atom.xml` probe, JS-only scrape, X via RSSHub). `RSSHUB_BASE_URL` empty means no RSSHub candidate. `_autodiscover_feed` returns the best non-scrape URL.
- **IN-05** [DONE] (P1·M) Platform recipes with tier labels: YouTube (`@handle`→channel_id feed), Reddit (`.rss` incl. `top.rss?t=`), Substack `/feed`, Bluesky + Mastodon profile RSS, GitHub releases/commits Atom, arXiv, podcasts (existing iTunes lookup + Podcast 2.0 `<podcast:transcript>` link stored). — Accept: resolver unit tests per platform; tier shown in UI. — Deps: IN-04 — Evidence: `platform_candidates` plus resolver tests for Reddit top, Bluesky, Mastodon, GitHub releases. GitHub is verified only after the candidate body has an rss/feed/rdf root, so a non-feed `releases.atom` falls through to `commits.atom`. `/r/top` stays a community feed; fosstodon.org and hachyderm.io use the same profile RSS recipe as mastodon.social. `transcript_url` is the first Podcast 2.0 transcript in the raw item XML (any namespace prefix). Migration 0011. Tiers for the new platforms are `fully_tracked` and the badge component has icons for them.
- **IN-07** [PARTIAL] (P1·M) Canonicalization + dedupe. — Evidence: `canonicalize_url` strips every `utm_*` key plus `fbclid`, `gclid`, `mc_cid`, `mc_eid`, and `igshid`, drops a leading `www`, keeps IPv6 brackets, and drops only the scheme's default port. A bad port returns None and that item is skipped. The dispatcher compares canonical forms of stored URLs for the same source, so a legacy `www` or tracking URL still matches. Embedding similarity and simhash are still IQ-01. Negative path test: different paths stay distinct.
- **IN-06** [TODO] (P2·M) Optional RSSHub bridge: `RSSHUB_BASE_URL`; route registry for platforms lacking native feeds; tier=best-effort; health-checked; disabled by default. — Accept: works against a local RSSHub container in compose profile `bridge`; off ⇒ no outbound calls. — Deps: IN-05
- **IN-08** [TODO] (P1·L) **Extraction cascade** (see prompt §Algorithms A2): feed full-content → trafilatura → readability fallback → Playwright render → give up visibly. Persist `extraction_method`, `extraction_confidence`, `page_type`; skip listing/collection/product pages from ranking. — Accept: cascade unit tests with fixtures per branch; failure state visible in UI. — Deps: P0-06, P0-07
- **IN-09** [TODO] (P1·M) Golden extraction corpus: ≥ 100 URLs (news, blogs, docs, newsletters, JS-heavy, non-English) with expected-snippet assertions (≤ 25 words each) + a script that snapshots pages **locally** (do not commit third-party pages); `make extract-eval` prints word-level F1 / snippet recall per method. — Accept: CI runs a small offline subset; article-type F1 ≥ 0.90 documented; regressions fail CI. — Deps: IN-08
- **IN-10** [TODO] (P2·M) Metadata: author, published_at (JSON-LD → OpenGraph → meta → feed), language detection, word count/reading time, lead-image URL (URL only), paywall flag (label, never bypass, D-08). — Accept: fixture tests; UI shows paywall badge. — Deps: IN-08
- **IN-11** [TODO] (P1·L) Newsletter inbound v2: provider-agnostic adapter interface; implementations: Cloudflare Email Worker→webhook, Postmark inbound, Mailgun routes, Resend inbound, IMAP poller (dedicated folder/label); per-user address with plus/hash token; provider signature/HMAC verification; replay protection. — Accept: sample MIME + webhook payload tests per adapter; unsigned/replayed requests rejected. — Deps: P0-06, P0-07
- **IN-12** [TODO] (P1·M) Newsletter parsing: prefer HTML part → sanitize → main-content extraction; strip tracking pixels; unwrap tracked links (SSRF-safe); "view in browser" URL; `List-Unsubscribe`; auto-create Source per sender; detect confirmation emails and surface the confirm link to the user; dedupe re-sends. — Accept: ≥ 15 real-world-style MIME fixtures (Substack, Beehiiv, Ghost, Mailchimp, plain text). — Deps: IN-11
- **IN-13** [TODO] (P2·M) Robust OPML import/export: nested folders→tags, 5k-feed file via async job with progress, duplicate handling, round-trip test. — Accept: import/export/import is idempotent. — Deps: P0-08
- **IN-14** [TODO] (P2·M) Importers: Feedly/Inoreader OPML (+ starred if exported), Instapaper/Raindrop/Readwise CSV ⇒ saved items with positive seed signal. — Accept: one fixture per format; imported items flagged `origin=import`. — Deps: IN-13
- **IN-15** [TODO] (P2·S) Backfill policy: on adding a source ingest last N (default 20), embed, but do not flood the next digest (cap per source per digest). — Accept: test. — Deps: –
- **IN-16** [TODO] (P2·M) Retention/storage: store cleaned text (raw HTML optional), configurable retention days, per-source cap, scheduled vacuum, storage stats in admin. — Accept: retention job test; DB growth documented. — Deps: –
- **IN-17** [TODO] (P2·S) Scraper etiquette: robots.txt check in scrape mode, per-host rate limit, kill-switch per domain, documented policy (D-08). — Accept: tests with robots fixtures. — Deps: IN-08
- **IN-18** [TODO] (P2·M) Ingestion observability: structured logs with `source_id`, metrics (fetch success %, extraction success % by method, ingest→scored lag), simple admin page. — Accept: metrics endpoint + dashboard screenshot in docs. — Deps: IN-08

### PHASE 2 — Intelligence v2  _(goal: rankings that are demonstrably better than chronological, and explainable)_

- **IQ-01** [TODO] (P0·M) Embedding provider abstraction + registry; per-row `embedding_model`, `embedding_dim`, `embedding_version`. — Accept: two models can coexist; queries filter by model. — Deps: P0-04
- **IQ-02** [TODO] (P1·L) Switch default to `nomic-embed-text-v1.5` (D-03): correct prefixes; pgvector HNSW (cosine) index; new column/table + dual-write + resumable backfill + cut-over flag + rollback; **golden retrieval check first** (same-topic pair retrieval MRR on ≥ 200 hand-labeled item pairs from fixtures) — switch only if it wins. Record results in ADR. — Accept: ADR with numbers; migration tested on a 50k-row DB; RAM impact documented; `lite` profile keeps MiniLM. — Deps: IQ-01
- **IQ-03** [TODO] (P1·M) Embedding input construction: `title + lead + body window(s)` instead of a truncated prefix (chunk up to 4 windows, pooled with title weight ×2). — Accept: test proves a long article's late-section topic shifts its vector vs prefix-only. — Deps: IQ-01
- **IQ-04** [TODO] (P0·M) **Feature contract + leakage rules** (Algorithms A3): `ScoreFeatures` dataclass, all 8 in [0,1], computable pre-consumption; `reading_depth` = *predicted* engagement from history (Beta-shrunk by source × cluster × length bucket), never the item's own telemetry. — Accept: test asserts feature functions never read the target item's interaction rows; docs table per signal. — Deps: P0-04
- **IQ-05** [TODO] (P1·L) Multi-interest profile (D-05): Ward/agglomerative clustering of the user's positively-engaged embeddings (distance threshold, not fixed k), medoid per cluster, recency-decayed importance, LLM-generated cached label; semantic score = importance-weighted max cosine over top-3 clusters, percentile-calibrated per user. — Accept: synthetic 2-topic user: multi-interest beats mean-vector on NDCG@10 by a documented margin. — Deps: IQ-01, IQ-16
- **IQ-06** [TODO] (P1·L) Discovery pool + candidate generation: (a) followed-source recents, (b) ANN neighbors of medoids from a **discovery corpus** (outbound links from followed items; curated seed feeds per topic; optional public aggregator feeds like HN/Lobsters/arXiv listings used only as candidate sources), (c) exploration sample. Items tagged `origin=followed|discovery|import|extension`. Caps to bound cost. — Accept: a fresh instance produces discovery-origin candidates; Suggestion signal can now fire. — Deps: IQ-05, IN-04
- **IQ-07** [TODO] (P0·M) Impression logging table `digest_impressions(user_id,item_id,digest_id,section,position,score,features_json,weights_version,exploration,propensity,shown_at)` + `digest_viewed` events. Every digest/feed render logs. — Accept: migration + tests; no unlogged path to the user. — Deps: P0-04
- **IQ-08** [TODO] (P0·M) Label definitions (Algorithms A4 table): bounce/partial/full/re-read/thumbs/save/skip→label∈[0,1] with confidence weights; skips only count when the digest was actually viewed. — Accept: table-driven unit tests; documented. — Deps: IQ-07
- **IQ-09** [TODO] (P1·M) Debiasing + exploration: ε-slots (min(2, ⌈10%·N⌉) per digest) sampled from ranks 6–40 ∝ softmax(score/T), propensity logged; per-position examination estimated from exploration items; clipped IPW (cap 5) in training; feature-flagged. — Accept: simulation with a position-biased click model shows debiased learner recovers true weights better than naive. — Deps: IQ-07, IQ-08, IQ-16
- **IQ-10** [TODO] (P0·L) Weight learning v2 (Algorithms A5): online pairwise logistic update, L2 shrinkage toward `w_prior`, LR decay, min-evidence gate (≥ 30 labeled pairs), simplex projection with floor 0.02, versioned history. — Accept: converges on synthetic users with a single dominant signal; stable with sparse data; no NaN/inf; weights history queryable. — Deps: IQ-04, IQ-08, IQ-16
- **IQ-11** [TODO] (P1·L) Temporal model v2: long (half-life ≈ 90–180 d), medium (14–28 d window, decays over 4–8 weeks), short (72 h saturation penalty), time-of-day histogram (drives digest time + length/type fit), per-user recency curve learned from fresh-vs-evergreen reads. — Accept: unit tests per scale; saturation test (6th article on same event ranks lower). — Deps: IQ-05
- **IQ-12** [TODO] (P1·M) Diversity re-rank: MMR (λ default 0.7) + 30% cluster cap + novelty slots (default 15%, configurable) + adaptive serendipity from 14-day cluster-entropy. — Accept: property tests: cap never exceeded, no near-duplicates, novelty share within ±1 item. — Deps: IQ-05
- **IQ-13** [TODO] (P1·M) Explainability: persist per-item `explanation` (per-signal contribution w·s, top matching cluster label(s), trust note, discovery flag); API + "Why this?" UI. — Accept: faithfulness test — contributions sum to the score within 1e-6. — Deps: IQ-10
- **IQ-14** [TODO] (P2·M) Trust v2: Beta posterior per source and per (creator, topic cluster), time-decayed, exposes credible interval; new sources start at prior. — Accept: unit tests incl. cold-start and decay. — Deps: IQ-08
- **IQ-15** [TODO] (P2·M) Content-quality features (no LLM required): length bucket, link/citation density, code-block presence, readability, originality heuristics; calibrated against the user's own read-through; optional LLM judge behind a flag with cache. — Accept: tests; ablation in eval report. — Deps: IN-08
- **IQ-16** [TODO] (P0·L) **Evaluation harness** `backend/eval/`: (a) replay metrics on logged impressions (NDCG@10, MAP, precision@k, MRR, coverage/diversity) vs baselines (chronological, source-priority, random, semantic-only); (b) synthetic-user simulator (persona vectors, drift, noise, position-biased clicks); (c) `make eval` writes a markdown report; fast synthetic suite runs in CI. — Accept: full PRS beats chronological baseline on synthetic users by a documented threshold; report committed under `docs/eval/`. — Deps: IQ-07 (replay part independent for synthetic)
- **IQ-17** [TODO] (P2·M) Performance + idempotency: vectorized scoring (numpy), HNSW ANN, Celery `acks_late` + idempotent tasks + task de-dup keys; budgets: digest build < 3 s for 1,000 candidates; ingest→scored p95 < 60 s. — Accept: benchmark script + numbers in docs. — Deps: IQ-02
- **IQ-18** [TODO] (P2·S) Ranker versioning: `ranker_version` stored on impressions; admin action "recompute scores"; idempotent backfills. — Accept: test. — Deps: IQ-10

### PHASE 3 — Digest & reader experience  _(goal: the product feels smart in daily use)_

- **UX-01** [TODO] (P1·M) Digest builder per spec: Lead (3–5), Creators (grouped by person), Deep reads (≥ 8 min), Discovery (labeled); saturation cap; dedupe. — Accept: unit tests on synthetic candidate sets. — Deps: IQ-12
- **UX-02** [TODO] (P2·S) Digest length personalization: target = clamp(1.25 × EMA(items opened per digest), 5, 30); explicit override. — Accept: test. — Deps: IQ-07
- **UX-03** [TODO] (P2·M) Scheduling: per-user timezone + preferred time (learned from open-time histogram), 1–4/day, idempotent send, "nothing worth reading" skip threshold. — Accept: no duplicate sends under retry; DST test. — Deps: IQ-11
- **UX-04** [TODO] (P1·L) Email v2: responsive HTML + plain text; 2–3 sentence summary; "why" line; **one-click 👍/👎/save signed links** (HMAC, expiring, no login); tracking pixel OFF by default; click-through via app redirect into the in-app reader (needed for telemetry, disclosed); `List-Unsubscribe`; SPF/DKIM docs. — Accept: rendered snapshot tests; signed-link tamper/expiry tests; feedback recorded. — Deps: P0-07, IQ-13
- **UX-05** [TODO] (P1·M) In-app reader v2: sanitized content, typography/theme controls, keyboard shortcuts (j/k/o/s/u/d), telemetry hardening (throttled batching, `sendBeacon` on unload, idle + visibility handling, minimum-time thresholds against false depth). — Accept: Playwright e2e for telemetry; unit tests for depth calc. — Deps: P0-07
- **UX-06** [TODO] (P1·M) Feedback UI + signal mapping: thumbs, reason tags (too basic / already knew / off-topic / wrong depth / clickbait), snooze topic, mute source, more/less-like-this ⇒ documented mapping table to signals and interest clusters. — Accept: table in docs + tests per mapping. — Deps: IQ-08
- **UX-07** [TODO] (P2·S) Early-feedback prompts: first 14 days, ≤ 3 per digest (depth level / more from this source / connection accuracy); auto-off after 14 days or dismissal; stored as labeled data. — Accept: test. — Deps: UX-04
- **UX-08** [TODO] (P2·M) Interest management UI: list/graph of clusters, raise/lower priority, temporary suppression with expiry, merge/rename, export/import profile JSON. — Accept: e2e. — Deps: IQ-05
- **UX-09** [TODO] (P2·L) Cross-source synthesis: cluster same-story items within 48 h (embedding sim + title/entity overlap) → one card with N perspectives; LLM 2–3 sentence synthesis with per-source attribution (cached); no-LLM fallback = grouped source list. — Accept: fixture stories collapse; LLM off still renders. — Deps: IQ-01, P0-05
- **UX-10** [TODO] (P2·M) Emerging-topics detector: distinct-source count per topic cluster in last 72 h vs 28-day baseline (z-score) ⇒ "Emerging" card. — Accept: synthetic burst detected, steady-state not. — Deps: IQ-05
- **UX-11** [TODO] (P1·M) Search: Postgres FTS (`tsvector`+GIN) + pgvector semantic, fused with RRF; filters (source/date/saved/origin). Gate: document whether FTS suffices before considering Meilisearch (D-09). — Accept: relevance tests on fixtures; p95 < 300 ms at 100k items. — Deps: IQ-02
- **UX-12** [TODO] (P2·S) Saved queue with intent semantics: save→read = strong positive; unopened after 14 d = slight negative. — Accept: test. — Deps: IQ-08
- **UX-13** [TODO] (P2·M) Settings: serendipity %, saturation cap, digest length/times, LLM status page, data export (JSON+OPML), delete-my-data. — Accept: export contains everything; delete verified. — Deps: –
- **UX-14** [TODO] (P2·M) Frontend quality: a11y pass (axe, 0 serious), dark mode, responsive, empty/error/loading states, i18n-ready strings. — Accept: axe CI check; Lighthouse ≥ 90 on reader. — Deps: –
- **UX-15** [TODO] (P3·M) Multilingual: language detection, per-user language filter, `bge-m3` profile, summaries in article or chosen language. — Accept: tests with 3 languages. — Deps: IQ-02

### PHASE 4 — Cold start & onboarding without a population

- **CS-01** [TODO] (P1·M) Onboarding v2: free-text interests → LLM expands to 8–15 subtopics + seed queries (user confirms/edits) → embeddings become initial clusters with prior weight; works without an LLM by embedding raw text. — Accept: e2e; LLM-off path. — Deps: IQ-05, P0-05
- **CS-02** [TODO] (P1·M) Starter packs: ≥ 20 topic OPML bundles (10–25 feeds each; URLs+titles only), one-click subscribe, liveness verified by script in CI (weekly). — Accept: ≥ 90% of feeds live at commit time. — Deps: IN-13
- **CS-03** [TODO] (P1·M) Calibration on the user's **own** ingested items: after initial backfill show 8–12 diverse items (k-means over candidates) for quick ratings; immediate cluster/weight update. — Accept: e2e; diversity assertion. — Deps: IQ-05, IN-15
- **CS-04** [TODO] (P1·M) Population-free warmup (D-06): shipped topic-prior model (taxonomy embeddings + default weights), import seeding, exploration boost for first 14 days; audit `cold_start/collaborative.py` for single-user behavior and make it a safe no-op behind `COLLAB_WARMUP` (enabled only when ≥ N users). — Accept: test proves single-user instance never errors or degrades; documented in addendum. — Deps: P0-04
- **CS-05** [TODO] (P1·S) First-digest quality gate: automated check (≥ 5 items, ≥ 3 clusters, ≥ 1 discovery, 0 duplicates, ≥ 80% with usable summaries) + persona e2e. — Accept: CI job. — Deps: CS-01..04
- **CS-06** [TODO] (P3·S) Local-only time-to-value stats (signup→first digest→first read) in an admin page; no external telemetry (D-07). — Accept: page + test. — Deps: –

### PHASE 5 — Ecosystem

- **EC-01** [TODO] (P2·L) PWA: manifest, service worker (offline digest + reader cache), install prompt, optional Web Push (VAPID). — Accept: Lighthouse PWA pass; offline e2e. — Deps: UX-05
- **EC-02** [TODO] (P2·L) Browser extension MV3 (Chrome + Firefox): detect feeds on page, one-click add source/creator, "save & rate this page" (`origin=extension`, strong signal), options for instance URL + token. Audit the existing `extension/` first. — Accept: packaged build, e2e against local instance. — Deps: EC-03
- **EC-03** [TODO] (P2·M) API tokens + stable versioned `/api/v1`, scoped tokens, published OpenAPI. — Accept: contract tests. — Deps: P0-09
- **EC-04** [TODO] (P2·L) MCP server: `get_digest`, `search_archive`, `list_sources`, `add_source`, `explain_item`, `record_feedback` (read-only by default; write scope opt-in). — Accept: works with an MCP client; scope tests. — Deps: EC-03
- **EC-05** [TODO] (P2·M) Obsidian/Logseq export: saved/highlighted items → Markdown + frontmatter into a folder/webhook. — Accept: golden-file tests. — Deps: UX-12
- **EC-06** [TODO] (P2·L) Discover-sources: suggest sources/creators from interest clusters (sources of discovery items read fully; sources cited by trusted sources) with accept/dismiss loop feeding Suggestion signal. — Accept: e2e; dismissals respected. — Deps: IQ-06
- **EC-07** [TODO] (P3·M) **Decision gate**: write ADR comparing (a) Google-Reader/Fever-compatible API façade returning ranked order and (b) "sidecar mode" importing subscriptions/read-state from Miniflux/FreshRSS. Implement only if the owner approves. — Accept: ADR with effort/benefit. — Deps: EC-03
- **EC-08** [TODO] (P3·M) Podcast/video: use description + Podcast 2.0 transcript tag when present; optional local Whisper (opt-in); no scraping of YouTube captions. — Accept: tests; tier=best-effort. — Deps: IN-05
- **EC-09** [DROPPED] (P3·–) Team digests — deferred until hosted option exists (D-10). Evidence: decision D-10.

### PHASE 6 — Release, docs, community

- **RL-01** [TODO] (P1·M) One-command install: compose profiles `lite` (no Browserless, MiniLM) and `full`, healthchecks, `make` targets, min-RAM per profile documented, images on GHCR with semver tags. — Accept: fresh VM install ≤ 10 min following docs. — Deps: IQ-02
- **RL-02** [TODO] (P1·L) Docs site (MkDocs/Docusaurus): quickstart, config reference (generated from settings), architecture, "how ranking works" with the math, FAQ, troubleshooting, upgrade guide, backup/restore, security model, privacy statement (what leaves your box). — Accept: link-checked in CI. — Deps: most of Phases 1–3
- **RL-03** [TODO] (P2·M) Demo mode: seed data + synthetic persona, `make demo`, README GIF/screenshots. — Accept: works offline. — Deps: CS-05
- **RL-04** [TODO] (P1·S) Backup/restore script + CI restore test; single-alembic-head check. — Accept: restore verified in CI. — Deps: –
- **RL-05** [TODO] (P2·S) Governance: CONTRIBUTING, CODE_OF_CONDUCT, SECURITY.md, issue/PR templates, Discussions categories, good-first-issue labels. — Accept: files present. — Deps: –
- **RL-06** [TODO] (P2·S) Benchmarks page: ranking eval, extraction F1 table, resource usage per profile. — Accept: reproducible commands. — Deps: IQ-16, IN-09
- **RL-07** [TODO] (P1·S) v0.1.0 release: changelog, notes, tag, GHCR images, release checklist executed. — Accept: GitHub Release published. — Deps: Exit Gate 6
- **RL-08** [TODO] (P2·S) Licensing hygiene: dependency license report (Python + npm), model-license notes for optional local models, AGPL implications noted for hosted forks. — Accept: `docs/licenses.md`. — Deps: OQ-01
- **RL-09** [DROPPED] (P3·–) Hosted-option prerequisites (multi-tenant isolation, billing, quotas, abuse controls) — backlog only until pull exists (D-10). Evidence: decision D-10.

---

## 5. Phase Exit Gates (all boxes must be checked, with evidence, before starting the next phase)

**Gate 0 — Audit & Stabilize**
- [x] Baseline + Spec Coverage Matrix complete; no `UNVERIFIED` rows. Baseline UI click-through was not done (P0-02 PARTIAL); tests cover register and onboarding.
- [x] LLM client provider-agnostic; retired model ids are rewritten, not called; digest summary test passes with the key unset (P0-05, `6c68dd9`)
- [x] `safe_fetch()` is the user-URL path (P0-06, `17f0d03`); XSS + XML suites green (P0-07/08, `95dd760`). Browserless DNS rebind is a documented residual (ADR 0003).
- [x] CI green on `main`. Backend run 35929735469 succeeded for the Phase 0 merge; frontend and CodeQL succeeded for that merge and for the Next 16.3.6 / fast-uri follow-ups. README, LICENSE, and `docs/ARCHITECTURE.md` match the code.
- [x] Backlog re-prioritized in Discoveries. No task ids were renumbered; the existing IQ-04/06/07/16 items already name the gaps the audit confirmed.

**Gate 1 — Ingestion**
- [ ] Extraction golden corpus: article-type F1 ≥ 0.90; extraction success ≥ 95% on article-type fixtures
- [ ] Polling scheduler + feed health verified with simulated failures
- [ ] Newsletter adapters (≥ 2 providers + IMAP) pass MIME fixtures; signature checks enforced
- [ ] Platform recipes + tiers visible; RSSHub bridge optional and off by default

**Gate 2 — Intelligence**
- [ ] Eval report committed: full PRS beats chronological, semantic-only and random baselines on synthetic users (thresholds in report)
- [ ] Embedding decision ADR with golden-retrieval numbers; migration tested with rollback
- [ ] Every ranked item carries a faithful explanation; feature-leakage test green
- [ ] Impression logging on 100% of user-visible paths

**Gate 3 — Digest & UX**
- [ ] Digest sections, length personalization, scheduling, email v2 with signed feedback links working end-to-end
- [ ] Search (FTS + vector) meets latency target; Meilisearch decision recorded
- [ ] a11y CI check green; keyboard-first reader

**Gate 4 — Cold start**
- [ ] First-digest quality gate passes for ≥ 5 synthetic personas
- [ ] Single-user instance never touches collaborative code paths

**Gate 5 — Ecosystem**
- [ ] PWA installable + offline digest; extension packaged; API tokens + MCP server documented

**Gate 6 — Release**
- [ ] Fresh-VM install ≤ 10 min from docs; backup/restore proven in CI; docs site live; v0.1.0 tagged

---

## 6. Spec Coverage Matrix (filled during P0-04)

Status values: `UNVERIFIED` → `EXISTS` / `PARTIAL` / `MISSING` / `DIVERGES`. Evidence = file paths + test names.

| # | Spec item (V2 proposal / README claim) | Status | Evidence / notes |
|---|-----------------------------------------|--------|------------------|
| A1 | RSS/Atom parsing + feed autodiscovery | PARTIAL | `rss_parser.py` parses RSS from bytes via feedparser. Autodiscovery tries a link tag then `/feed`, `/rss`, `/atom.xml`, `/feed.xml`, `/rss.xml`, `/feed/rss`. No platform-recipe cascade, no RSSHub (IN-04). |
| A2 | Scraping: trafilatura + Playwright fallback (Browserless) | EXISTS | `scraper.py`: robots, `safe_fetch`, trafilatura, then Browserless. Block responses are not escalated when `scraper_respect_blocks` is true. |
| A3 | Newsletter forwarding address | PARTIAL | Mailgun inbound webhook only (`api/newsletter.py`), HMAC + replay window. No Cloudflare/Postmark/Resend/IMAP adapters (IN-11). |
| A4 | Creator resolution across platforms | PARTIAL | `creator/resolver.py`: Substack, YouTube, Medium, Reddit, blog autodiscovery, podcasts via iTunes. X and LinkedIn return unsupported. |
| A5 | Platform tier labelling | EXISTS | `PLATFORM_CAPABILITIES` in `resolver.py`; badges in `CreatorProfile.tsx` / `AddCreatorForm.tsx`. |
| A6 | Fault-tolerant ingestion with user notification | PARTIAL | Scraper retries and per-source health fields exist (`test_source_health_surfaced`). No adaptive scheduler, no dead-feed digest notice (IN-02, IN-03). |
| A7 | OPML import | PARTIAL | `POST /sources/import-opml` and onboarding import via listparser. Now size- and entity-limited. No nested-folder tags, no export round-trip (IN-13). |
| B1 | Embeddings on ingest | EXISTS | `utils/embeddings.py`: `all-MiniLM-L6-v2`, dimension hard-coded 384, `Vector(384)`. Text is title + brief, sliced to 2048 chars. No HNSW migration, no model column (IQ-01). |
| B2 | Signal 1 semantic alignment | DIVERGES | `signals/semantic.py` scores against interest-graph node embeddings and bridge midpoints. Not cluster medoids, not percentile-calibrated (IQ-05). |
| B3 | Signal 2 reading depth | DIVERGES | Telemetry columns and `useReadingTelemetry.ts` exist (migration 0003). The signal is a similarity-weighted mean of historical completion (`reading_depth.py`) and the SQL does not exclude the candidate's own interaction row (IQ-04). |
| B4 | Signal 3 suggestion — non-followed pool? | PARTIAL | `suggestion.py` boosts similarity to items flagged `was_suggested` and read ≥ 85%. The only producer of that flag is digest serendipity (`builder.py` `_select_serendipity_candidates`), which needs public items from sources the user does not follow. A one-user database does not create those items. No discovery corpus (IQ-06). |
| B5 | Signal 4 explicit feedback | PARTIAL | Thumbs and a few reason strings in `explicit_feedback.py` and `FeedbackBar.tsx`. Not the roadmap's tag-to-cluster mapping (UX-06). |
| B6 | Signal 5 trust | PARTIAL | `source_trust.py` is per-source from behavior. Creator×topic Beta posteriors are not there (IQ-14). |
| B7 | Signal 6 content quality | PARTIAL | `content_quality.py` uses length, citations, depth score. Not the logistic feature set in A3 (IQ-15). |
| B8 | Signal 7 temporal: 3 scales + time-of-day | PARTIAL | `temporal_context.py` blends long/medium/short weights from settings. No learned time-of-day histogram (IQ-11). |
| B9 | Signal 8 novelty / 15% serendipity | PARTIAL | `novelty.py` plus `serendipity_percentage` (default 15) and a diversity nudge in `builder.py`. Not MMR, not a cluster cap at selection time beyond the section builder's topic cap (IQ-12). |
| B10 | PRS + learned weights; leakage? | DIVERGES | `scorer.py` weighted sum. `meta_weights.py` gradient steps; `reading_depth` and `explicit_feedback` are held out of the gradient (`LEAKING_SIGNALS`) but still used as features, and reading_depth can see the target row. Not the pairwise logistic learner (IQ-10). |
| B11 | Interest graph | PARTIAL | Nodes, edges, decay in `interest_graph/`. No interest-shift detector, no medoids (IQ-05). |
| B12 | Explainability | PARTIAL | Signal breakdown and a "why" string reach the email template and the card tooltip. Contributions are not guaranteed to sum to the score (IQ-13). |
| B13 | Semantic dedupe | PARTIAL | Digest builder clusters items at cosine ≥ 0.88 and keeps one. Not the canonical-URL / simhash cascade (IN-07). |
| B14 | Saturation cap 30% | PARTIAL | `sections.py` `max_topic_pct=0.30` counts `topic_clusters` strings, not embedding clusters. |
| C1 | Onboarding | EXISTS | `cold_start/onboarding.py`: free text, sample ratings, OPML, starter sources. LLM topic extract falls back to keywords. |
| C2 | Collaborative warmup, one user | EXISTS | Returns `[]` below `collaborative_warmup_min_users` (default 1000). `test_collaborative.py`. Flag default is still enabled; the threshold makes a single user a no-op. |
| C3 | Early feedback prompts (first 2 weeks) | MISSING | No first-14-days prompt cap. UX-07. |
| D1 | Digest sections | EXISTS | `sections.py`: lead, creator, deep_reads, discovery. Deep read threshold is `reading_time_minutes > 10`, not ≥ 8. |
| D2 | Digest length personalization | PARTIAL | `builder.py` adjusts length from engagement history. Not the EMA formula in A6 (UX-02). |
| D3 | Email + one-click feedback | PARTIAL | SMTP via `utils/email.py` (Zoho by default, not Resend). Template autoescapes. Unsubscribe links exist. No signed thumbs/save links (UX-04). |
| D4 | Cross-source synthesis + emerging topics | PARTIAL | Synthesis of near-duplicate clusters in `builder.py` calls the LLM and no-ops when it returns empty. No emerging-topic z-score (UX-10). |
| D5 | Summaries + which model ids | DIVERGES | Three lengths, Redis cache. Models are settings, default `openai/gpt-oss-120b` / `openai/gpt-oss-20b`. Extractive fallback. `summary_source` column (migration 0007). |
| D6 | Topic suppression with expiry | EXISTS | `suppressed_until` from migration 0002, used by the interest graph. |
| E1 | Search (spec: Meilisearch) | PARTIAL | Meilisearch client in `utils/search.py` and `/api/v1/search`. No Postgres FTS. D-09 says FTS first; the code already has Meilisearch. UX-11 is the gate. |
| E2 | PWA / offline / push | PARTIAL | `frontend/public/manifest.json` and `sw.js` exist. No installability pass, no Web Push (EC-01). |
| E3 | Browser extension | PARTIAL | MV3 popup/background/options. Adds the current page as source or creator. No `browser_specific_settings` (Firefox is unverified). No "save and rate" signal. Host permission is localhost:8000 and readprism.app. EC-02. |
| E4 | Obsidian / Notion / Logseq | PARTIAL | `integrations/export.py`: Obsidian markdown, Notion API, Readwise. No Logseq. |
| E5 | Discover-new-sources | MISSING | No accept/dismiss source suggestions. EC-06. |
| E6 | Team digests | DIVERGES | Tables and `api/teams.py` exist. D-10 drops the product (EC-09). Code remains. |
| E7 | Self-host docs | PARTIAL | `docs/` has deployment, privacy, terms, launch, competitors, this tracker, architecture, security. Not a docs site (RL-02). |
| E8 | Auth and security | PARTIAL | bcrypt, JWT access+refresh rotation, rate limits, SSRF, nh3, XML limits, secret-key boot check. See `docs/security.md`. IP pinning for HTTPS is not done. |
| E9 | Tests + CI | PARTIAL | 232 pytest passed on this branch. CI: `.github/workflows/backend.yml` (ruff, mypy, pytest, alembic head), `frontend.yml` (tsc, build), `codeql.yml`. Lint script is broken. Actions not run on this branch. |
| E10 | Frontend pages incl. `/read/[id]` | EXISTS | App Router pages listed by `next build` (20 routes), including `/read/[id]`, digest, feed, sources, creators, search, onboarding via register, marketing `/vs/*`. |

---

## 7. Audit results (P0-02..P0-04 output goes here)

### Baseline

Recorded 2026-09-24 on the tree at `37b7f16` before the phase-0 edits, except where noted.

| Check | Result |
|---|---|
| `docker compose up -d db redis` | Up. db ~78 MiB, redis ~20 MiB. Compose does not publish 5432 to the host. |
| `docker compose build backend` | Finished. Torch wheel 454 MB (CUDA packages on linux/arm). Image id `8506d6c8122c`. |
| Alembic | Single head `0006` before this branch. `0007` applied after the summary_source migration. |
| pytest (pre-change) | 205 passed, 6 warnings, 11.72s |
| pytest (this branch) | 232 passed, 9 warnings, 11.24s. Command: image `readprism-backend` with `pip install nh3==0.3.7 defusedxml==0.7.1` because that image was built from the previous requirements file, then `python -m pytest tests/ -q`. |
| ruff check + format | Clean before and after. |
| mypy 3.11 | 14 errors before, 0 after (`mypy app --python-version 3.11 --ignore-missing-imports`). |
| `tsc --noEmit` | Exit 0 before and after the CSP / DOMPurify edit. |
| `npm run build` | Exit 0. Banner said Next.js 16.2.11; `package.json` says 16.2.12. |
| `npm run lint` | Exit 1. `next lint` is gone in Next 16. |
| Coverage | Not measured. |
| UI walkthrough | Not done. See P0-02. |

### Summary of `extension/` and `docs/` contents

`extension/` is a Manifest V3 unpacked extension: `manifest.json`, `popup.html`/`popup.js`, `background.js`, `options.html`/`options.js`, `icon.svg`, `README.md`. It stores an instance URL and bearer token and POSTs the current page as a source or a creator. It does not capture reading telemetry.

`docs/` before this session: deployment, privacy, terms, launch notes, competitors, unit economics, media shot list, cold-start contingency, one ADR (Celery solo pool). This session added PROGRESS, ROADMAP, ARCHITECTURE, security, two ADRs, and the spec addendum. `audit/` at the repo root is a separate 00–17 product audit plus an implementation log; it is not the task tracker.

---

## 8. Discoveries (bugs, surprises, spec conflicts)

- 2026-09-24 · P0-04 · `feedparser.parse(url)` fetched the feed itself and skipped SSRF checks. · Fixed in `17f0d03` by parsing bytes from `safe_fetch`.
- 2026-09-24 · P0-04 · Suggestion/serendipity has no candidate source on a one-user database. The query excludes the user's own sources and nothing else ingests public items. · Already IQ-06. No new id.
- 2026-09-24 · P0-04 · `reading_depth.py` nearest-neighbor query does not exclude the candidate item, so a re-score after the user has read it can use that item's own completion. · Already IQ-04.
- 2026-09-24 · P0-04 · Collaborative warmup is a no-op under 1000 active users (`collaborative.py`). It does not throw. · Matches D-06. CS-04 still owns the flag default (`cold_start_collaborative_enabled=True` with the threshold).
- 2026-09-24 · P0-04 · README said a hosted option is planned. D-10 says it is not the plan. · README sentence updated in `28f9b42`.
- 2026-09-24 · P0-04 · `source._is_starter = True` was written and never read. · Removed while clearing mypy (`2e93706`).
- 2026-09-24 · P0-03 · `npm run lint` calls removed `next lint` and fails. Frontend CI does not run it. · Left as P0-11 partial. Do not "fix" by exiting 0.
- 2026-09-24 · P0-02 · sentence-transformers 3.4.1 on this Docker build pulled torch 2.14 plus CUDA wheels for linux/arm (~454 MB). A `lite` image should not do that. · Already RL-01 / D-09. Not changed here.
- 2026-09-24 · P0-03 · `next build` printed 16.2.11 while `package.json` pins 16.2.12. · Not investigated past the banner. P0-12's Next bump is a separate PR.
- 2026-09-24 · P0-06 · HTTPS `safe_fetch` does not pin the connection to the resolved IP, so a rebind after the check can still land on a private address. Browserless has the same window. · Documented in ADR 0003. Not fixed; pinning breaks certificate checks if done naively.
- 2026-09-24 · P0-10 · OQ-01 stays open. `LICENSE` and the README are both AGPL-3.0. The owner still has to confirm that was intended.
- 2026-09-24 · review · PR #55 CI: mypy failed because the CI job installs celery (and therefore redis) without `types-redis`, plus `email.message` payload typing. CodeQL alert gate failed on `py/full-ssrf` inside `safe_fetch` (the guard itself). CodeRabbit: gzip double-decode, HTML pages skipped autodiscovery, JSON newsletter signature dropped, token bucket hang, extractive cache TTL, reader CSP blocked Next inline scripts. · Fixed on the branch. CodeQL on the guard is the same false positive class as alerts 11/12/27.

No backlog ids were reprioritized. The audit confirmed the existing order: impressions and labels (IQ-07, IQ-08) before weight learning, and a discovery corpus (IQ-06) before the suggestion signal can mean what the spec says.

---

## 9. Session Log (append-only, newest first)

### Session 2 — 2026-09-24

CodeRabbit on PR #59 (12 comments): GitHub feeds are fetched before `is_verified`; a bad port no longer aborts the batch; default ports are scheme-specific; IPv6 hosts stay bracketed; every `utm_*` key is stripped; `/r/top` is a community; fosstodon.org and hachyderm.io get profile RSS; feed confirmation requires an XML root; well-known probes run two at a time and stop on the first hit; stored URLs are canonicalized before dedupe; transcript lookup uses the podcast namespace and the first tag in the raw item. pytest 288 passed. ruff 0.6.9 check and format clean. Pushed to `agent/phase-1-recipes`.

Tasks touched: pulled `main` at `a485e45`. P0-11 DONE (CI green on main). P0-12 DONE (owner merged #53 and #54). IN-01 DONE.

Evidence: `test_second_fetch_of_unchanged_feed_is_304_and_skips_parse`. pytest 237 passed. Alembic head `0008`.

Blockers: none. Gate 0 is now checked.

Next 3 tasks: IN-03 feed health in the UI, IN-04 autodiscovery cascade, IN-08 extraction cascade (build the golden corpus in IN-09 before tuning).

IN-02 landed in the same session. pytest 249 passed. Alembic head `0009`. The 301 URL rewrite is tested as a function and not yet applied inside `safe_fetch`, which follows the redirect and keeps the final URL.

### Session 1 — 2026-09-24

Tasks touched: P0-01 DONE, P0-02 PARTIAL, P0-03 DONE, P0-04 DONE, P0-05 DONE, P0-06 DONE, P0-07 DONE, P0-08 DONE, P0-09 DONE, P0-10 DONE, P0-11 PARTIAL, P0-12 PARTIAL, P0-13 DONE.

Evidence: commits `6c68dd9`, `17f0d03`, `95dd760`, `2e93706`, `28f9b42` on `agent/phase-0-audit-stabilize`. pytest 232 passed. mypy clean. ruff clean. `tsc --noEmit` clean. `npm run build` clean. Alembic head `0007`.

Blockers / questions raised: OQ-01 still open (AGPL confirmed in the file, not confirmed by the owner). Gate 0 CI-on-main is unchecked because this branch is not merged. P0-12 bumps were not built.

Next 3 tasks: wait for CI on PR #55 (https://github.com/mohitmishra786/readprism/pull/55); P0-12 only after `next@16.3.6` and `fast-uri@3.1.8` are built; do not start Phase 1 until the owner reviews this audit.

## Session 1 report — 2026-09-24

Done: P0-01 DONE. P0-02 PARTIAL (no UI click-through). P0-03 DONE. P0-04 DONE. P0-05 DONE. P0-06 DONE. P0-07 DONE. P0-08 DONE. P0-09 DONE. P0-10 DONE. P0-11 PARTIAL (mypy + alembic head added; Actions not run; lint script broken). P0-12 PARTIAL (PRs #53 and #54 left open). P0-13 DONE.

Evidence: SHAs above. `python -m pytest tests/ -q` → 232 passed, 11.24s. `mypy app --python-version 3.11 --ignore-missing-imports` → success, 113 files. ruff check and format clean. Frontend tsc and production build clean.

Findings: feedparser fetched URLs itself; suggestion has no one-user candidate pool; reading_depth can include the target row; collaborative warmup is already a no-op under 1000 users; llama model ids were the configured defaults and are now a denylist; `next lint` is gone; the backend image pulls CUDA torch on arm.

Decisions: ADR 0002 (LLM client), ADR 0003 (`safe_fetch`). No decision-log row was overturned.

Blocked/Asks: OQ-01 (please confirm AGPL-3.0). Whether to merge Dependabot #53 and #54. Gate 0 stays open on "CI green on main" until this branch lands.

Next: owner review. Then P0-11 (push / CI) and P0-12, then Phase 1 starting at IN-01.

