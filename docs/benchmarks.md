# Benchmarks

<p class="lead">Reproducible numbers. Re-run any row with the command in its
"How" column.</p>

*Last verified: 2026-10-02. Commit SHAs for each run are in the session
evidence in `docs/PROGRESS.md`.*

## Ranking quality (synthetic eval, CI-enforced)

`make eval` (backend/scripts/rank_eval.py; gate: PRS ≥ chronological + 0.05)

| Ranker | NDCG@10 |
|---|---|
| **PRS (learned)** | **0.7784** |
| Semantic-only | 0.6365 |
| Chronological | 0.6269 |
| Random | 0.6122 |

Also CI-asserted: exploration/IPW recovery under position bias, diversity
cap never exceeded, explanation contributions sum to the score (1e-6),
label table per A4.

## Extraction quality (golden corpus, offline)

`make extract-eval` (100 generated pages: 80 articles, 20 listings; gate:
article word-F1 ≥ 0.90 and snippet recall ≥ 0.90)

| Metric | Result |
|---|---|
| Article word-F1 | ≥ 0.90 (gate) |
| Snippet recall | ≥ 0.90 (gate) |
| Extraction success (articles) | ≥ 95% |

## Extraction on real pages (#230)

52 real published pages (13 each from the Go blog, the Rust blog, the
Kubernetes blog and Wikipedia), with ground truth taken from each page's own
Markdown or plain-text source in a public, permissively licensed repository
(licences per page in `backend/tests/fixtures/real_pages/manifest.json`).
Collected 2026-10-20 with `backend/scripts/collect_real_pages.py`; scored by
`evaluate_real()` and gated in `test_real_page_extraction.py`.

| Source | Pages | Precision | Recall | Word F1 |
|---|---|---|---|---|
| Go blog | 13 | 0.970 | 0.997 | 0.983 |
| Rust blog | 13 | 0.995 | 0.999 | 0.997 |
| Kubernetes blog | 13 | 0.992 | 0.994 | 0.993 |
| Wikipedia | 13 | 0.860 | 0.997 | 0.922 |
| **All** | **52** | **0.954** | **0.997** | **0.974** |

Nothing a reader needs is lost (recall ≥ 0.99 everywhere). Wikipedia was
0.641 precision / 0.774 F1 until #319, because MediaWiki reference lists and
`[1]` citation markers were extracted as article text; they are now removed
before extraction (generic footnotes and data tables are kept). The rest of
the Wikipedia gap is data tables: real content, but the plain-text ground
truth leaves them out. The sample covers three static-site generators and
MediaWiki, not yet WordPress, Ghost or Substack.

## Retrieval / embedding decision (IQ-02)

`make retrieval-eval` (200 fixture pairs; ADR 0004)

| Input | MRR |
|---|---|
| Full text | 1.00 |
| 8-token prefix (MiniLM truncation) | 0.75 |

## Starter-pack liveness (CS-02)

`make starter-pack-check` (weekly CI gate ≥ 90%)

| Measure | Result (2026-10-02) |
|---|---|
| Packs / feeds | 21 / 211 |
| Live feeds | **211/211 (100%)** |

## First-digest quality gate (CS-05)

CI (pytest `test_first_digest_gate.py`, 5 personas × real builder):
≥ 5 items, ≥ 3 clusters, ≥ 1 discovery, 0 duplicates, ≥ 80% summaries:
all pass.

## Resource profile (compose)

| Profile | Services | Notes |
|---|---|---|
| lite (default) | 8 | No Browserless; hash embeddings; search = Postgres FTS+pgvector |
| full | +2 | Browserless (rendered extraction) + egress proxy |

Idle RSS measured 2026-09-24: db ~78 MiB, redis ~20 MiB. Backend full image
includes torch (CUDA wheels on arm ≈ 454 MB extra); `:latest-lite` image
skips torch/sentence-transformers entirely (RL-01).

## Lighthouse (#216, #315)

Lighthouse 12 (simulated mobile) on a production build (`next start`)
against the compose API, Apple M4 / 16 GB, headless Chromium, 2026-10-20.
Ranges are over 2 to 3 runs. Landing is measured as an anonymous visitor (signed-in users are
redirected to their digest). Reproduce with `frontend/scripts/lighthouse.sh
<content_id>`. Lighthouse 12 has no PWA category; offline reading is
covered by `e2e-stack/offline-pwa.spec.ts`.

| Page | Performance | Accessibility | Best practices | SEO |
|---|---|---|---|---|
| Landing `/`, before #315 | 81 to 84 | 100 | 79 | 100 |
| Landing `/`, after #315 | **89 to 91** | 100 | **100** | 100 |
| Reader `/read/<id>` (signed in) | 86 to 87 | 95 | 96 | 66 |

#315 removed every third-party request from the landing page (fonts
self-hosted with `next/font`; hero images served from this origin as WebP;
the proxy had been sending a 4.3 MB PNG) and made the headline paint with
the first frame instead of after its fade-in delay.

Reader, not counted as defects or tracked elsewhere:
- SEO 66 is `is-crawlable`: `/read/` is disallowed in `robots.txt` on
  purpose (private, signed-in pages).
- Accessibility 95: in OS dark mode the article text is near-invisible, #316.
- Best practices 96: a fresh test account has no digest yet, so the reader's
  next/previous lookup (`/digest/latest`) logs a 404.
- Performance: real paint is ~150 ms; the simulated LCP counts the article
  being rendered client-side after its API call.

## Digest build at 1,000 candidates and 1,000 users (#192)

`backend/scripts/bench_digest_build.py` on a throwaway database: 1,000 fresh
items across 200 shared feeds (384-d embeddings around 24 topic centres),
1,000 onboarded users following every feed with 6 interests each. In
process, sequential, no Celery. Apple M4 / 16 GB, Postgres 16 + pgvector in
Docker, 2026-10-20.

| Measure | Result |
|---|---|
| `rank()` on 1,000 candidates, one user | p50 166 ms, max 300 ms (5 runs) |
| Full `build_digest()` per user (x1,000) | p50 1.61 s, p95 3.18 s, max 4.82 s |
| 1,000 builds, one process | 30.5 min total |

The ranker is a small share of a build; most of the time is the queries and
writes around it (impressions, stories, preferences). p95 is just over the
3 s budget; part of the run overlapped another local test run, so treat the
tail as approximate. Daily builds spread over each user's send time and the
digest workers, so 1,000 users is ~30 min of single-worker time per day.

The first 1,000-user run crashed: every subscriber's source row for the
user's feeds was bound as its own SQL parameter, and past asyncpg's 32,767
limit (here 200 feeds x 1,000 users) every digest build failed. Fixed in
the same change (ids bound as one array).

Candidate window (#313): builds used to rank an arbitrary 200 window items
(no ordering). They now rank the newest items, at most
`DIGEST_PER_SOURCE_CAP` per feed, up to `DIGEST_CANDIDATE_LIMIT` (1,000).
Story clustering was pure-Python and took ~12 s at 1,000 candidates; it is
now one matrix product per item. Same machine, 50 users, 400 feeds x 3
items (1,000 candidates after the per-feed cap):

| Builder | Candidates ranked | p50 | p95 |
|---|---|---|---|
| Before (#313) | 200, arbitrary | 808 ms | 907 ms |
| After | 1,000, newest per feed | 429 ms | 476 ms |

## Hybrid search at 100,000 items (#231, #311)

`backend/scripts/bench_search.py` on a throwaway database: one user's
archive of 100,000 items in 300 feeds, `GET /api/v1/search` called in
process (ASGI) for 20 queries x 5 rounds after a warm-up, every query text
unique so the query-vector cache never helps. Apple M4 / 16 GB, Postgres 16
+ pgvector in Docker, 2026-10-20. Budget: p95 < 300 ms.

| Measure | Result |
|---|---|
| p50 | 18 ms |
| p95 | **29 ms** |
| max | 108 ms |
| MiniLM query encode alone (uncached) | p50 3.6 ms, p95 4.9 ms |

Both legs ran (Postgres FTS on `search_tsv`, pgvector HNSW), fused with RRF;
every query returned a full page of 20. Items and queries are embedded by
the same MiniLM model. The first #231 run (p95 52 ms) used hash vectors on
both sides, because search embedded queries with the hash fallback even on
the standard image; #311 fixed that, and these numbers include real query
inference.
