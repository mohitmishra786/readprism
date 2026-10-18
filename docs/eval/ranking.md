# Ranking Eval (Synthetic Benchmark)

> [!NOTE]
> **Synthetic Sanity Check Only:**
> This benchmark measures learner mechanics and gradient convergence on synthetically
> generated users and i.i.d. random feature vectors with single-feature dominance.
> It does **not** evaluate real-world human reading satisfaction or real-world item ranking quality.
> Production engagement is evaluated on observed user interactions via `scripts/ranking_eval.py`.

## Method
Synthetic users, one dominant signal each. Weights are learned with
pairwise updates on a training split. PRS is the held-out score
from those weights, not a sort of the labels. Chronological keeps
ingest order. Semantic-only uses the first feature. Random is a
permutation. No-learning uses fixed uniform prior weights without updates.
Oracle sorts directly by true held-out relevance (upper bound).
NDCG@10 is the mean across users.

## Baselines
- PRS NDCG@10 (learned): 0.9509
- Oracle NDCG@10 (upper bound): 1.0000
- No-learning NDCG@10 (default prior weights): 0.7368
- Semantic-only NDCG@10: 0.6365
- Chronological NDCG@10: 0.6269
- Random NDCG@10: 0.6122

## Margins & Gate
- Margin over chronological: 0.3239
- Margin over no-learning: 0.2141

Gate: PRS beats each non-oracle baseline (chronological, semantic-only, random, no-learning) by at least 0.05.
Passed: True

## Retrieval & Latency Fixtures
Retrieval fixture (200 pairs, no Nomic weights): see `make retrieval-eval`.
A tie between the two candidates scores expected reciprocal rank 0.75.
Default embedding stays all-MiniLM-L6-v2 because the stored column is 384-d.
See ADR 0004.

Linear score of a 1000 by 8 feature matrix is covered by
`test_exploration_ipw_and_eval_gate`. A full digest build against
1,000 database rows was not timed. Celery sets `task_acks_late`.
Task de-dup keys are `task_dedup_key`.
