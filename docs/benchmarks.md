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
| lite (default) | 8 | No Browserless/Meilisearch; hash embeddings; search = Postgres FTS+pgvector |
| full | +2 | Browserless (rendered extraction) + Meilisearch (dormant, operator opt-in) |

Idle RSS measured 2026-09-24: db ~78 MiB, redis ~20 MiB. Backend full image
includes torch (CUDA wheels on arm ≈ 454 MB extra); `:latest-lite` image
skips torch/sentence-transformers entirely (RL-01).

## Not yet measured (named)

- Search p95 latency at 100k items (budget: < 300 ms) — load benchmark
  pending (RL-06 follow-up).
- Digest build wall-time at 1,000 candidates against a loaded DB (budget:
  < 3 s).
