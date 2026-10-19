# Offline replay: pre-registered protocol (#200)

Fixed before any owner data is run, so the numbers can't be tuned after the fact.

**Question.** On a real reader's own logs, does PRS rank what they went on to read above what newest-first and trust-only rankings would have shown?

**Data.** One account export (format 2+: interactions, digests, digest items, article metadata). It runs on the reader's own machine with `backend/scripts/replay_eval.py`. No raw data is committed; only the aggregate report is.

**Split (leave-last-week-out).** Digests from the last 7 days are the test set. Rankers learn only from interactions created before the first test digest.

**Candidates.** The items each test digest actually showed.

**Relevant.** Fully read (completion ≥ 0.85 or reached the end), saved, or rated up.

**Rankers.**
- **PRS:** `score_candidates` on a state rebuilt from training data only, with default contract weights. Articles and interests are re-embedded locally; exported vectors don't exist.
- **Newest first.**
- **Trust only:** the feed's finish rate in the training data (Laplace-smoothed), with newest first on ties.

**Metrics.** NDCG@10 and Recall@5 per test digest, averaged over test digests with at least one relevant item.

**What counts as a result.** PRS beats newest-first on NDCG@10. With a single reader and about 7 digests this is evidence, not significance; the report states the counts.

**Known limits.**
- Candidates are what was *shown*, so items PRS would have surfaced but never showed can't be scored.
- Learned meta-weights are not used, to avoid leakage from the test week.

Reports go in this folder as `replay-YYYY-MM-DD.md`.
