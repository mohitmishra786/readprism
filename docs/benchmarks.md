# Benchmarks

Reproducible numbers. Re-run any row with the command in its "How" column.
Last verified: 2026-10-02 (see docs/PROGRESS.md session evidence for SHAs).

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
| Wikipedia | 13 | 0.641 | 0.997 | 0.774 |
| **All** | **52** | **0.899** | **0.997** | **0.937** |

Nothing a reader needs is lost (recall ≥ 0.99 everywhere). On Wikipedia the
extractor also keeps reference lists and data tables, which the plain-text
ground truth leaves out, so precision drops; that's a known gap, not fixed
here. The sample covers three static-site generators and MediaWiki, not yet
WordPress, Ghost or Substack.

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
≥ 5 items, ≥ 3 clusters, ≥ 1 discovery, 0 duplicates, ≥ 80% summaries —
all pass.

## Resource profile (compose)

| Profile | Services | Notes |
|---|---|---|
| lite (default) | 8 | No Browserless; hash embeddings; search = Postgres FTS+pgvector |
| full | +2 | Browserless (rendered extraction) + egress proxy |

Idle RSS measured 2026-09-24: db ~78 MiB, redis ~20 MiB. Backend full image
includes torch (CUDA wheels on arm ≈ 454 MB extra); `:latest-lite` image
skips torch/sentence-transformers entirely (RL-01).

## Lighthouse (#216)

Lighthouse 12 on a production build (`next start`) against the compose API,
Apple M4 / 16 GB, headless Chromium, 2026-10-20. Reproduce with
`frontend/scripts/lighthouse.sh <content_id>`. Lighthouse 12 dropped its PWA
category; offline reading is covered by the `e2e-stack/offline-pwa.spec.ts`
test instead.

| Page | Performance | Accessibility | Best practices | SEO |
|---|---|---|---|---|
| Landing `/` | 66 | 100 | 79 | 100 |
| Reader `/read/<id>` (signed in) | 81 | 95 | 96 | 66 |

Below the 90 target: landing performance (LCP 4.7 s, total blocking time
470 ms) and best practices (Google Fonts sets third-party cookies); reader
performance (LCP 4.2 s) and SEO (a private, signed-in page without a meta
description). Tracked as follow-ups, not fixed here.

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

Note: the builder fetches at most 200 items from the window with no
ordering, so with more than 200 fresh items it ranks an arbitrary subset.
Follow-up, not changed here.

## Not yet measured (named)

- Search p95 latency at 100k items (budget: < 300 ms), #231.
