# 05 — AI/ML Ranking Engine Audit (Core IP)

*Evidence: line-level review of `backend/app/services/ranking/**` and `interest_graph/**`, July 2026.*

## Status Snapshot

- **The 8-signal PRS is real and implemented**, not aspirational. `scorer.py` computes all eight, weights via per-user meta-weights, clamps to [0,1]. This is the strongest part of the project.
- **Per-user gradient descent is real, not a stub** (`meta_weights.py::update_meta_weights`): squared-error gradient, step 0.01, per-weight clamp [0.01, 0.50], renormalize, DB-persisted, gated behind ≥20 interactions. It is a genuine single-layer linear update as the spec describes.
- **But the learning target is questionable** and several signals are proxies that will need empirical validation before any "it learns" claim is credible.
- Cold-start mechanisms: onboarding **implemented**, starter-source seeding **implemented**, collaborative warmup **implemented but inert at low N** and mislabeled, feedback prompts **implemented**.
- Interest graph: nodes/edges/decay/core-promotion all **implemented**. "Directed" and "transitive relevance" are **partially** honored — edges are stored directed but used undirected, and transitive relevance (scoring via 2-hop graph connections) is **not actually computed** anywhere; the semantic signal uses a weighted-average interest *vector*, not graph traversal.

## Signal-by-signal reality

| # | Signal | Implemented? | Empirical risk |
|---|---|---|---|
| 1 Semantic | Yes — cosine(content emb, weighted-avg interest vector), mapped [0,1] via `(sim+1)/2` | Averaging all node embeddings into one vector **collapses multi-interest users to their centroid** — a person into both cooking and compilers gets a vector near neither. This is the classic averaged-embedding failure. Graph clusters exist but aren't used to segment the vector. **High risk.** |
| 2 Reading depth | Yes — pgvector kNN over past-read items weighted by completion | Needs ≥5 completed reads to activate; sound design. Depends entirely on telemetry quality (artifact 09). Cosine-similarity `(sim+1)/2` floors at 0.5 so "dissimilar" never scores below neutral — compresses the signal. Medium risk. |
| 3 Suggestion | Yes — `was_suggested` boosts graph-update weight (1.2 vs 0.8 in `updater.py`) | The *purest signal* per spec, but as a PRS **input** it's thin: `suggestion.py` (2.3KB) mostly rewards items from non-followed sources. The high-value part (learning from suggestion reads) lives in graph update, not scoring. OK. |
| 4 Explicit feedback | Yes — thumbs/reasons/saves in `feedback.py` | Solid; highest-confidence signal. |
| 5 Source trust | Yes — learned per-source + per-creator-per-topic (`creator_trust`), nudged ±0.02/interaction | Good design; the per-creator-per-topic trust is genuinely differentiated. Cold value 0.4–0.5. |
| 6 Content quality | Yes — length/citations/originality heuristics | Heuristic; `is_original_reporting` needs an LLM or is null. Tie-breaker weight (0.05) appropriate. |
| 7 Temporal | Yes — long/medium/short 3-scale + time-of-day, session saturation penalty | Most sophisticated signal (`temporal_context.py`, 6.3KB). Many magic constants (0.5/0.35/0.15 blend, 0.80 saturation threshold, ±0.05 ToD) — **all unvalidated guesses.** Medium risk, but well-built. |
| 8 Novelty | Yes — peaks at novelty=0.35, falls off both sides | The novelty-vs-quality tension the spec worries about is hard-coded to a fixed target, not learned. Will need tuning. |

## The core empirical problems (these need data, not code)

1. **The meta-learning target may be circular.** `update_meta_weights` regresses learned weights so that `predicted = Σ wᵢ·signalᵢ` matches an `actual` engagement score = `0.5·completion + 0.3·rating + 0.2·saved`. But `reading_depth` (signal 2) is itself derived from completion, and `explicit_feedback` (signal 4) from rating — so the model is partly predicting its own inputs. Weights on those signals will inflate for reasons that don't reflect genuine predictive value. **This must be validated on held-out digests, not just "it converges."**
2. **Averaged interest vector** (signal 1) is the single biggest quality risk — see table. Multi-topic users are exactly ICP #1 (deep niche + breadth). Consider per-cluster vectors and taking the max similarity across clusters.
3. **Transitive relevance is claimed but not computed.** No code walks `InterestEdge` to score an item at the intersection of two nodes. The graph is built and decayed but only its node embeddings feed scoring (via the average). The spec's headline capability is, functionally, **not yet built**.
4. **Explainability is real** (`why_ranked`, `_top_signals` show contribution %). But it explains *signal* contributions, not the *graph* connections the spec promised ("connects your interest in X with your recent Y"). The promised explanation type isn't generated.
5. **Collaborative warmup is inert and mislabeled.** `collaborative.py` selects "similar users" but (a) the candidate query is `LIMIT 200` arbitrary users, not similarity-ranked despite the comment; (b) similarity depends on other users' `interest_vec` being warm in Redis — cold cache → skipped; (c) at low N there are no similar users. It will do nothing at launch and little until thousands of active users. That's acceptable *if* the spec stops calling it a day-1 cold-start pillar.

## Checklist

- [ ] P0 | Validate the ranking on held-out data before claiming "it learns": for the concierge cohort, measure whether predicted-PRS rank correlates with actual next-day reads | The entire IP claim rests on this and it is currently unmeasured | `meta_weights.py`; no eval harness in repo | M | founder+eng
- [ ] P0 | Replace single averaged interest vector with per-cluster vectors + max-similarity | Averaged embedding silently degrades exactly the multi-interest ICP | `signals/semantic.py::_get_user_interest_vector` | M | eng
- [ ] P0 | Remove input/target leakage from meta-learning (don't let signals derived from completion/rating predict a completion/rating-based target) or explicitly hold those out | Circular target inflates weights and invalidates the learning story | `meta_weights.py::update_meta_weights` | M | eng
- [ ] P1 | Actually implement transitive/graph relevance (2-hop edge traversal contributing to score) or drop the claim from all copy | Headline capability is currently vaporware | `interest_graph/*`; no traversal in scorer | L | eng
- [ ] P1 | Generate graph-based explanations ("connects X and Y") to match the promised explainability | Current explanations are signal %s, not the promised topic connections | `delivery.py::_top_signals` | M | eng
- [ ] P1 | Reframe collaborative warmup as a >1k-user feature; fix the similarity-ranking bug or gate it off until then | Silent no-op sold as a cold-start pillar | `collaborative.py` | S | eng
- [ ] P1 | Un-floor cosine signals (allow <0.5 for genuine mismatch) or document the intentional compression | Half the signal range is unused, blunting discrimination | multiple `signals/*.py` `(sim+1)/2` | S | eng
- [ ] P2 | Make novelty target and temporal blend weights learnable or at least config-exposed | Currently unvalidated magic constants | `novelty.py`, `temporal_context.py` | M | eng
- [ ] P2 | Add an offline ranking-eval notebook to the repo (nDCG / read-prediction AUC per cohort) | Turns "trust me it learns" into a demoable graph — great for the dev ICP and the blog | none | M | eng

## Top 5 if you only do 5 things

1. Build the held-out ranking-eval harness; you cannot honestly market learning without it.
2. Fix the averaged-interest-vector collapse (per-cluster max-sim).
3. Break the meta-learning target/​input circularity.
4. Either implement transitive graph relevance or stop claiming it.
5. Stop calling collaborative warmup a day-1 pillar until it can actually fire.

**Revisit trigger:** re-run after the eval harness produces its first per-cohort accuracy curve.
