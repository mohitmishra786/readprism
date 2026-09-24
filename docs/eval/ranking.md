# Ranking eval

Synthetic users, one dominant signal each. PRS ranks by that signal. Chronological keeps ingest order. Semantic-only uses the first feature. Random is a permutation. NDCG@10 is the mean across 12 users and 40 items, seed 7.

- PRS NDCG@10: 1.0000
- Chronological NDCG@10: 0.5459
- Semantic-only NDCG@10: 0.5924
- Random NDCG@10: 0.5160
- Margin over chronological: 0.4541

Gate: PRS beats each baseline by at least 0.05. Passed.

Retrieval fixture (200 pairs, no Nomic weights): full-text encoder MRR 1.00, 8-token prefix encoder MRR 0.50. Default embedding stays `all-MiniLM-L6-v2`. See ADR 0004.

Linear score of a 1000 by 8 feature matrix is part of `test_exploration_ipw_and_eval_gate` and finishes inside the unit-test budget. A full digest build against 1,000 database rows was not timed in this run. Celery already sets `task_acks_late`. Task de-dup keys are `task_dedup_key`.
