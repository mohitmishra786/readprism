"""Tests for digest section construction — saturation caps, sectioning, serendipity.

The SectionBuilder is pure (no I/O), so we test it directly with constructed
ContentItem-like objects. This exercises the rules the spec promises:
- per-topic saturation limits (no topic > 30% of digest)
- discovery bucketing from origin=discovery / _serendipity_candidate
- deep-reads eligibility by reading time (>= 8 minutes)
- creator-section grouping (max 2 per creator, contiguous per person)
- lead section of 3-5 non-exploration items
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
    origin: str = "followed",
    exploration: bool = False,
):
    item = MagicMock()
    item.id = uuid.uuid4()
    item.topic_clusters = topics or []
    item.reading_time_minutes = reading_time
    item.creator_platform_id = creator_id
    item.origin = origin
    breakdown = {"_serendipity_candidate": serendipity}
    if exploration:
        breakdown["exploration"] = True
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


def test_discovery_section_takes_origin_discovery_items():
    """origin=discovery items land in discovery even without the internal flag."""
    discovery_item = _make_item(origin="discovery", prs=0.4)
    followed_item = _make_item(origin="followed", prs=0.1)  # low PRS is NOT discovery
    builder = SectionBuilder(total_items=10, serendipity_pct=20)

    sections = builder.build([followed_item, discovery_item])

    discovery_ids = {it.id for it, _, _ in sections["discovery"].items}
    assert discovery_item[0].id in discovery_ids
    assert followed_item[0].id not in discovery_ids


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


def test_deep_reads_threshold_is_eight_minutes():
    """Deep-read eligibility is reading_time >= 8 minutes."""
    builder = SectionBuilder(total_items=10)
    assert builder.is_deep_read_eligible(_make_item(reading_time=15)[0]) is True
    assert builder.is_deep_read_eligible(_make_item(reading_time=8)[0]) is True
    assert builder.is_deep_read_eligible(_make_item(reading_time=7)[0]) is False


def _fillers(count: int, prs: float = 0.95) -> list:
    """High-PRS generic items used to saturate the lead section first."""
    return [_make_item(topics=[f"filler{i}"], prs=prs - i * 0.01) for i in range(count)]


def test_deep_reads_section_holds_eight_minute_items():
    """An 8-minute item reaches the deep_reads section; a 7-minute one does not."""
    builder = SectionBuilder(total_items=20)
    eight = _make_item(reading_time=8, prs=0.5)
    seven = _make_item(reading_time=7, prs=0.6)
    sections = builder.build([*_fillers(5), seven, eight])

    deep_ids = {it.id for it, _, _ in sections["deep_reads"].items}
    assert eight[0].id in deep_ids
    assert seven[0].id not in deep_ids


def test_lead_section_is_three_to_five_items():
    """Lead holds 3-5 items for every digest size that can supply them."""
    # Small digest (N=5): 3 leads.
    builder5 = SectionBuilder(total_items=5)
    assert builder5.lead_count == 3
    # Medium (N=10): 4.
    builder10 = SectionBuilder(total_items=10)
    assert builder10.lead_count == 4
    # Large (N=20+): capped at 5.
    builder20 = SectionBuilder(total_items=20)
    assert builder20.lead_count == 5
    builder100 = SectionBuilder(total_items=100)
    assert builder100.lead_count == 5


def test_lead_excludes_exploration_items():
    """Exploration slots never take a lead position (A6: non-exploration leads)."""
    exploration_item = _make_item(prs=0.95, exploration=True)
    normal_item = _make_item(prs=0.5)
    builder = SectionBuilder(total_items=10)

    sections = builder.build([exploration_item, normal_item])

    lead_ids = {it.id for it, _, _ in sections["lead"].items}
    assert exploration_item[0].id not in lead_ids
    assert normal_item[0].id in lead_ids


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


def test_creator_section_groups_items_by_person():
    """Items from the same creator are contiguous; creators ordered by best PRS."""
    alice, bob = uuid.uuid4(), uuid.uuid4()
    # Interleaved input: bob(0.6), alice(0.5), bob(0.4), alice(0.45),
    # after five filler items saturate the lead section.
    rows = [
        *_fillers(5),
        _make_item(creator_id=bob, prs=0.60),
        _make_item(creator_id=alice, prs=0.50),
        _make_item(creator_id=bob, prs=0.40),
        _make_item(creator_id=alice, prs=0.45),
    ]
    builder = SectionBuilder(total_items=20)
    sections = builder.build(rows)

    creators = [it.creator_platform_id for it, _, _ in sections["creator"].items]
    assert len(creators) == 4
    # Bob has the best PRS (0.6 > 0.5), so bob's items come first.
    assert creators == [bob, bob, alice, alice]
    # Contiguity: no creator appears in two separated runs.
    seen_once: dict = {}
    for pos, cid in enumerate(creators):
        if cid in seen_once and seen_once[cid] != pos - 1:
            raise AssertionError(f"creator {cid} is not contiguous")
        seen_once[cid] = pos


def test_lead_section_respects_max_count():
    """Lead section holds at most lead_count items (3-5, scaled)."""
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


def test_creator_section_rechecks_topic_saturation():
    """Creator rows cannot overflow the topic cap at emit time (CodeRabbit).

    Lead already holds one "ai" item; three more "ai" creator rows all pass
    the preselection check individually, so the emit loop must recheck.
    """
    builder = SectionBuilder(total_items=12, max_topic_pct=0.30)  # cap = 3
    a, b = uuid.uuid4(), uuid.uuid4()
    rows = [
        _make_item(topics=["ai"], prs=0.95),  # lead -> ai count is 1
        *_fillers(3, prs=0.90),
        _make_item(topics=["ai"], creator_id=a, prs=0.80),
        _make_item(topics=["ai"], creator_id=a, prs=0.75),
        _make_item(topics=["ai"], creator_id=b, prs=0.70),
        _make_item(topics=["ai"], creator_id=b, prs=0.65),
    ]
    sections = builder.build(rows)

    ai_total = sum(
        1
        for section in sections.values()
        for it, _, _ in section.items
        if "ai" in (it.topic_clusters or [])
    )
    assert ai_total <= 3
    assert len(sections["creator"].items) == 2  # third "ai" row was skipped
