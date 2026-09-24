# Ranking eval

Synthetic users, one dominant signal each. Weights are learned with pairwise updates on a training split. PRS is the held-out score from those weights, not a sort of the labels. Chronological keeps ingest order. Semantic-only uses the first feature. Random is a permutation. NDCG@10 is the mean across users.

- PRS NDCG@10: 0.7784
- Chronological NDCG@10: 0.6269
- Semantic-only NDCG@10: 0.6365
- Random NDCG@10: 0.6122
- Margin over chronological: 0.1515

Gate: PRS beats each baseline by at least 0.05.
Passed: True

Retrieval fixture (200 pairs, no Nomic weights): see `make retrieval-eval`. A tie between the two candidates scores expected reciprocal rank 0.75. Default embedding stays all-MiniLM-L6-v2 because the stored column is 384-d. See ADR 0004.

Linear score of a 1000 by 8 feature matrix is covered by `test_exploration_ipw_and_eval_gate`. A full digest build against 1,000 database rows was not timed. Celery sets `task_acks_late`. Task de-dup keys are `task_dedup_key`.
