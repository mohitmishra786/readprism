"""Team-draft interleaving of PRS vs newest-first (#130)."""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models.content import ContentItem, UserContentInteraction
from app.models.digest import DigestImpression
from app.models.source import Source
from app.models.user import User
from app.services.ranking.interleaving import (
    BASELINE,
    PRS,
    digest_outcome,
    team_draft,
)


@pytest.mark.parametrize("seed", range(20))
def test_team_draft_is_fair_and_complete(seed):
    a = list(range(10))
    b = list(reversed(range(10)))
    drafted = team_draft(a, b, random.Random(seed))
    items = [item for item, _ in drafted]
    teams = [team for _, team in drafted]
    assert sorted(items) == a  # every item exactly once
    for k in range(1, len(teams) + 1):  # teams never drift apart by more than one pick
        prefix = teams[:k]
        assert abs(prefix.count(PRS) - prefix.count(BASELINE)) <= 1
    first_prs = next(item for item, team in drafted if team == PRS)
    first_base = next(item for item, team in drafted if team == BASELINE)
    assert first_prs == 0 and first_base == 9  # each team starts with its own top pick


def test_identical_rankings_split_evenly():
    drafted = team_draft([1, 2, 3, 4], [1, 2, 3, 4], random.Random(1))
    assert [item for item, _ in drafted] == [1, 2, 3, 4]
    teams = [team for _, team in drafted]
    assert teams.count(PRS) == teams.count(BASELINE) == 2


def test_digest_outcome_credits_finished_items():
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    teams = {a: PRS, b: BASELINE, c: PRS}
    read = SimpleNamespace(read_completion_pct=0.9, explicit_rating=None, saved=False)
    bounce = SimpleNamespace(read_completion_pct=0.1, explicit_rating=None, saved=False)
    assert digest_outcome(teams, {a: read, b: bounce}) == PRS
    assert digest_outcome(teams, {b: read}) == BASELINE
    assert digest_outcome(teams, {a: read, b: read}) == "tie"
    assert digest_outcome(teams, {}) == "tie"


@pytest.mark.asyncio
async def test_interleaved_digest_logs_teams_and_reports_win_rate(client, db_session, monkeypatch):
    from app.config import get_settings
    from app.services.digest.builder import build_digest

    monkeypatch.setattr(get_settings(), "ranking_interleaving", True)
    monkeypatch.setattr(get_settings(), "digest_per_source_cap", 20)
    user = User(email=f"il{uuid.uuid4().hex[:6]}@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    src = Source(user_id=user.id, url="https://il.example", feed_url="https://il.example/f")
    db_session.add(src)
    await db_session.flush()
    now = datetime.now(UTC)
    for i in range(10):
        db_session.add(
            ContentItem(
                source_id=src.id,
                url=f"https://il.example/{i}",
                title=f"Item {i}",
                fetched_at=now - timedelta(hours=i),
                published_at=now - timedelta(hours=i),
                word_count=300 + 150 * i,
                topic_clusters=[f"t{i}"],
            )
        )
    await db_session.commit()

    digest = await build_digest(user, db_session)
    await db_session.commit()

    impressions = list(
        (
            await db_session.execute(
                select(DigestImpression).where(DigestImpression.digest_id == digest.id)
            )
        ).scalars()
    )
    teams = [imp.team for imp in impressions]
    assert teams and set(teams) <= {PRS, BASELINE} and PRS in teams and BASELINE in teams

    prs_items = {imp.content_item_id for imp in impressions if imp.team == PRS}
    surfaced = (
        await db_session.execute(
            select(UserContentInteraction).where(UserContentInteraction.user_id == user.id)
        )
    ).scalars()
    for ix in surfaced:  # the user finishes the PRS team's picks
        if ix.content_item_id in prs_items:
            ix.read_completion_pct, ix.opened_at = 0.95, now
    await db_session.commit()

    from app.api import metrics

    monkeypatch.setattr(metrics.settings, "metrics_token", "t-interleave")
    report = (
        await client.get(
            "/api/v1/metrics/interleaving", headers={"X-Metrics-Token": "t-interleave"}
        )
    ).json()
    assert report["digests"] >= 1
    assert report["pooled"]["prs_wins"] == 1 and report["pooled"]["prs_win_rate"] == 1.0
    assert report["users"] == 1 and report["user_win_rates"] == [1.0]
    assert str(user.id) not in str(report)  # no user ids in operator output (#224)
