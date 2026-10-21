# weirling-rank

Explainable, personalized recommendation ranker for feeds and reading digests. Extracted from [Weirling](https://github.com/mohitmishra786/weirling).

`weirling-rank` is a pure-Python library with zero database or network dependencies (only requiring NumPy). It scores candidate items against a user profile using a vectorized pass and provides exact per-signal decompositions and human-readable explanations.

## Eight Pre-Consumption Signals

Every feature score is normalized into `[0.0, 1.0]` and computable before the user sees the item:

1. **semantic**: Cosine similarity to interest graph medoids and bridge topics.
2. **reading_depth**: Similarity-weighted historical completion of related articles.
3. **suggestion**: Historical completion rate for discovery items.
4. **explicit_feedback**: Closeness to positively rated articles minus closeness to negatively rated ones.
5. **source_trust**: Beta posterior of user engagement outcomes on the feed.
6. **content_quality**: Length, citation density, and depth heuristics shrunk toward user reading patterns.
7. **temporal_context**: Blended age curve (long-term, medium-term, and fresh) with saturation penalty.
8. **novelty**: Distance from recent reading history peaking at the user target.

Signals without evidence stay at neutral `0.5` and are recorded in `no_data`.

## Installation

```bash
pip install weirling-rank
```

## Quickstart

```python
import numpy as np
from datetime import datetime, UTC
from weirling_rank import (
    Candidate,
    UserRankingState,
    Interest,
    rank_candidates,
    SIGNALS,
)

# 1. Define candidate items with embeddings and metadata
vec_a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
vec_b = np.array([0.0, 1.0, 0.0], dtype=np.float32)

cand_a = Candidate(
    id="article-1",
    title="Deep Dive into Distributed Systems",
    embedding=vec_a,
    word_count=1200,
    has_citations=True,
    published_at=datetime.now(UTC),
)
cand_b = Candidate(
    id="article-2",
    title="Cooking Perfect Pasta",
    embedding=vec_b,
    word_count=600,
    published_at=datetime.now(UTC),
)

# 2. Build user ranking state with interest clusters and weights
user_state = UserRankingState(
    user_id="user-123",
    weights={s: 1.0 / len(SIGNALS) for s in SIGNALS},
    interests=[
        Interest(vector=vec_a, importance=1.0, label="Distributed Systems"),
    ],
    prefers_fresh=True,
    novelty_target=0.35,
)

# 3. Rank candidates
scored = rank_candidates(user_state, [cand_a, cand_b])

for item in scored:
    print(f"{item.item.title}: PRS = {item.prs:.3f}")
    print(f"  Explanation: {item.explanation}")
    print(f"  Component features: {item.features}")
```

## License

Apache-2.0
