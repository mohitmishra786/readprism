"""The demo persona looks like a real reader's digest (#158)."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("seed_demo", ROOT / "scripts" / "seed_demo.py")
seed_demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed_demo)


def test_content_is_fictional_and_licensed():
    data = json.loads(seed_demo.DATA.read_text())
    assert "CC0" in data["_about"] and "fictional" in data["_about"]
    assert len(data["articles"]) >= 25
    for art in data["articles"]:
        assert not re.search(r"demo story \d", art["title"])
        assert art["pub"] in {p["slug"] for p in data["publications"]}


@pytest.mark.asyncio
async def test_demo_digest_has_varied_scores_and_real_explanations(db_session):
    from app.models.content import ContentItem
    from app.models.digest import DigestItem

    summary = await seed_demo.seed(db_session, password="demo-password-123")
    await db_session.commit()
    assert summary["digest_items"] >= 10

    rows = (
        await db_session.execute(
            select(DigestItem, ContentItem)
            .join(ContentItem, ContentItem.id == DigestItem.content_item_id)
            .where(DigestItem.digest_id == summary["digest_id"])
            .order_by(DigestItem.position)
        )
    ).all()
    scores = [float(di.prs_score) for di, _ in rows]
    assert len({round(s, 3) for s in scores}) >= len(scores) // 2  # not all 0.498
    assert max(scores) - min(scores) >= 0.05
    explanations = [di.signal_breakdown.get("explanation", "") for di, _ in rows]
    assert all(explanations)
    assert not any(e.startswith("New to ReadPrism") for e in explanations)

    # The learned preferences show: the persona's main interest beats the
    # topics they skipped for two weeks.
    by_topic: dict[str, list[float]] = {}
    for di, item in rows:
        by_topic.setdefault(item.topic_clusters[0], []).append(float(di.prs_score))
    best_db = max(by_topic["database internals"])
    skipped = by_topic.get("home gardening", []) + by_topic.get("amateur football", [])
    assert all(best_db > s for s in skipped)

    # Re-running replaces the demo world instead of duplicating it.
    again = await seed_demo.seed(db_session, password="demo-password-123")
    await db_session.commit()
    count = (
        (
            await db_session.execute(
                select(ContentItem).where(ContentItem.url.like("https://%.demo.readprism.local/%"))
            )
        )
        .scalars()
        .all()
    )
    assert len(count) == len(json.loads(seed_demo.DATA.read_text())["articles"])
    assert again["digest_items"] >= 10
