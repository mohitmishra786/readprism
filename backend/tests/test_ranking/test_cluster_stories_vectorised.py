"""Vectorised story clustering gives the same stories as the original (#313)."""

from __future__ import annotations

import random
import time
from types import SimpleNamespace

import pytest

from app.services.digest.synthesis import (
    EMBED_THRESHOLD,
    MIN_TITLE_TOKENS,
    TITLE_THRESHOLD,
    cluster_stories,
    title_overlap,
    title_tokens,
)


def _cosine(left, right):
    left_sq = sum(v * v for v in left) ** 0.5
    right_sq = sum(v * v for v in right) ** 0.5
    if left_sq <= 1e-8 or right_sq <= 1e-8:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=False)) / (left_sq * right_sq)


def reference(items, embed_threshold=EMBED_THRESHOLD, title_threshold=TITLE_THRESHOLD):
    """The pre-#313 implementation, kept verbatim as the oracle."""
    clusters = []
    for index, item in enumerate(items):
        placed = False
        for cluster in clusters:
            seed = items[cluster[0]]
            seed_vec, item_vec = seed.embedding, item.embedding
            similar = False
            if seed_vec is not None and item_vec is not None:
                similar = _cosine(list(seed_vec), list(item_vec)) >= embed_threshold
            elif seed_vec is None and item_vec is None:
                similar = (
                    title_overlap(seed.title, item.title) >= title_threshold
                    and len(title_tokens(seed.title)) >= MIN_TITLE_TOKENS
                    and len(title_tokens(item.title)) >= MIN_TITLE_TOKENS
                )
            if similar:
                cluster.append(index)
                placed = True
                break
        if not placed:
            clusters.append([index])
    return clusters


WORDS = "apple earnings chip launch rust compiler release vacuum postgres raft leader vote".split()


def _items(rng: random.Random, n: int, dim: int = 32):
    centres = [[rng.gauss(0, 1) for _ in range(dim)] for _ in range(6)]
    items = []
    for _ in range(n):
        if rng.random() < 0.25:
            vec = None  # no embedding: title path
        elif rng.random() < 0.05:
            vec = [0.0] * dim  # degenerate vector
        else:
            c = rng.choice(centres)
            noise = rng.choice([0.05, 0.3, 0.6, 1.5])  # near-dups through to unrelated
            vec = [x + rng.gauss(0, noise) for x in c]
        title = " ".join(rng.sample(WORDS, rng.randint(2, 6)))
        items.append(SimpleNamespace(embedding=vec, title=title))
    return items


@pytest.mark.parametrize("seed", range(25))
def test_same_clusters_as_the_original(seed):
    items = _items(random.Random(seed), 120)
    assert cluster_stories(items) == reference(items)


def test_fast_at_1000_candidates():
    rng = random.Random(7)
    items = [
        SimpleNamespace(embedding=[rng.gauss(0, 1) for _ in range(384)], title=f"t{i}")
        for i in range(1000)
    ]
    start = time.perf_counter()
    clusters = cluster_stories(items)
    # ~0.1 s on a laptop; the old pure-Python version took ~12 s. A loose
    # bound keeps this meaningful without failing on a busy machine.
    assert time.perf_counter() - start < 4.0
    assert len(clusters) == 1000  # random vectors: no stories
