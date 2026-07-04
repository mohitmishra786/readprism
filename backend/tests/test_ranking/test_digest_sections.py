"""Tests for digest section construction — saturation caps, sectioning, serendipity.

The SectionBuilder is pure (no I/O), so we test it directly with constructed
ContentItem-like objects. This exercises the rules the spec promises:
- per-topic saturation limits (no topic > 30% of digest)
- discovery/serendipity bucketing from _serendipity_candidate
- deep-reads eligibility by reading time
- creator-section dedup (max 2 per creator)
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from app.services.digest.sections import SectionBuilder


def _make_item(
    topics: list[str] | None = None,
    reading_time: int = 5,
    creator_id=None,
    serendipity: bool = False,
    prs: float = 0.7,
):
    item = MagicMock()
    item.id = uuid.uuid4()
    item.topic_clusters = topics or []
    item.reading_time_minutes = reading_time
    item.creator_platform_id = creator_id
    breakdown = {"_serendipity_candidate": serendipity}
    return item, prs, breakdown


def test_discovery_section_only_takes_serendipity_candidates():
    """Only items flagged _serendipity_candidate go to the discovery section."""
    serendipity_item = _make_item(serendipity=True, prs=0.6)
    normal_item = _make_item(serendipity=False, prs=0.9)
    builder = SectionBuilder(total_items=10, serendipity_pct=20)

    sections = builder.build([normal_item, serendipity_item])

    discovery_ids = {it.id for it, _, _ in sections["discovery"].items}
    assert serendipity_item[0].id in discovery_ids
    assert normal_item[0].id not in discovery_ids


def test_topic_saturation_caps_one_topic():
    """A single topic cannot exceed max_topic_pct of the digest."""
    builder = SectionBuilder(total_items=10, max_topic_pct=0.30)
    # 8 items all on the same topic; cap = floor(10 * 0.30) = 3
    same_topic = [_make_item(topics=["ai"]) for _ in range(8)]
    sections = builder.build(same_topic)

    lead_topic_count = sum(
        1 for it, _, _ in sections["lead"].items if "ai" in (it.topic_clusters or [])
    )
    # Lead section should not exceed the saturation cap for the "ai" topic.
    assert lead_topic_count <= 3


def test_deep_reads_requires_long_reading_time():
    """Only items > 10 min reading time are deep-read eligible."""
    builder = SectionBuilder(total_items=10)
    long_item = _make_item(reading_time=15, prs=0.5)
    short_item = _make_item(reading_time=3, prs=0.5)

    assert builder.is_deep_read_eligible(long_item[0]) is True
    assert builder.is_deep_read_eligible(short_item[0]) is False


def test_creator_section_dedup_max_two_per_creator():
    """At most 2 items per creator make it into the creator section."""
    cid = uuid.uuid4()
    # 5 items from the same creator
    creator_items = [_make_item(creator_id=cid, prs=0.6) for _ in range(5)]
    builder = SectionBuilder(total_items=20)
    sections = builder.build(creator_items)

    creator_section_ids = [it for it, _, _ in sections["creator"].items]
    # The creator section caps each creator at 2.
    assert len(creator_section_ids) <= 2


def test_lead_section_respects_max_count():
    """Lead section holds at most lead_count items (min(5, 40% of total))."""
    builder = SectionBuilder(total_items=20)
    items = [_make_item(topics=[f"topic{i}"], prs=0.9 - i * 0.01) for i in range(15)]
    sections = builder.build(items)

    assert len(sections["lead"].items) <= 5
    assert len(sections["lead"].items) >= 1


def test_no_double_use_across_sections():
    """An item placed in one section is not reused in another."""
    builder = SectionBuilder(total_items=20)
    items = [
        _make_item(topics=["ai"], reading_time=15, serendipity=False, prs=0.8),
        _make_item(topics=["ml"], reading_time=3, serendipity=True, prs=0.5),
    ]
    sections = builder.build(items)

    used: set = set()
    for section in sections.values():
        for it, _, _ in section.items:
            assert it.id not in used, f"Item {it.id} reused across sections"
            used.add(it.id)
