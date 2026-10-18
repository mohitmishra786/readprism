"""MMR diversity before section layout (#148)."""

from __future__ import annotations

import uuid

import numpy as np

from app.models.content import ContentItem
from app.services.digest.builder import diversify_ranked
from app.services.digest.sections import SectionBuilder


def _row(vec, topic, prs):
    item = ContentItem(
        id=uuid.uuid4(),
        url=f"https://d.example/{uuid.uuid4().hex}",
        title="t",
        topic_clusters=[topic],
    )
    v = np.asarray(vec, dtype=np.float32)
    item.embedding = (v / np.linalg.norm(v)).tolist()
    return (item, prs, {})


def _axis(i, j=None, w=0.0):
    v = np.zeros(384)
    v[i] = 1.0
    if j is not None:
        v[j] = w
    return v


def test_near_duplicates_collapse_and_topics_interleave():
    same_story = [_row(_axis(0, 1, k / 1000), "outage", 0.9 - k / 100) for k in range(5)]
    varied = [_row(_axis(2 + k), f"topic{k}", 0.6) for k in range(5)]
    ranked = diversify_ranked(same_story + varied)

    outage = [r for r in ranked if r[0].topic_clusters == ["outage"]]
    assert len(outage) == 1  # cosine >= 0.92 duplicates dropped
    assert ranked[0][0].topic_clusters == ["outage"]  # the best item still leads
    assert len(ranked) == 6


def test_a_single_topic_cannot_flood_the_digest():
    flood = [_row(_axis(0, 3 + k, 0.6), "ai", 0.9) for k in range(20)]
    others = [_row(_axis(40 + k), f"other{k}", 0.5) for k in range(10)]
    ranked = diversify_ranked(flood + others)
    sections = SectionBuilder(total_items=12).build(ranked)
    placed = [row for sec in sections.values() for row in sec.items]
    share = sum(1 for item, _, _ in placed if item.topic_clusters == ["ai"]) / len(placed)
    assert share <= 0.34
    assert len(placed) >= 10


def test_small_lists_pass_through():
    rows = [_row(_axis(0), "a", 0.5), _row(_axis(1), "b", 0.4)]
    assert diversify_ranked(rows) == rows
