"""Team-draft interleaving: is PRS better than newest-first for this user? (#130)

Each interleaved digest merges two rankings of the same candidates: the PRS
ranking ("prs") and a baseline ("baseline": newest first). Teams take turns
picking their best not-yet-picked item; a coin flip decides who picks first
whenever both have picked equally often. Every item is assigned to exactly
one team, logged on its impression.

Outcome per digest: an item "wins" for its team when the user finished it
(completion >= 0.7, rated up, or saved). The team with more wins takes the
digest; equal counts are a tie. Over many digests the PRS win rate among
decided digests is the test of the product's core claim (PRODUCT_PLAN §1).
"""

from __future__ import annotations

import random
import uuid
from collections import Counter
from collections.abc import Hashable, Sequence
from datetime import UTC, datetime, timedelta

PRS = "prs"
BASELINE = "baseline"
FINISHED_COMPLETION = 0.7


def team_draft(
    prs_order: Sequence[Hashable], baseline_order: Sequence[Hashable], rng: random.Random
) -> list[tuple[Hashable, str]]:
    """Interleave two rankings of the same items; returns (item, team) in order."""
    picked: list[tuple[Hashable, str]] = []
    used: set = set()
    counts = {PRS: 0, BASELINE: 0}
    cursors = {PRS: 0, BASELINE: 0}
    lists = {PRS: list(prs_order), BASELINE: list(baseline_order)}
    total = len(set(lists[PRS]) | set(lists[BASELINE]))
    while len(picked) < total:
        if counts[PRS] < counts[BASELINE]:
            team = PRS
        elif counts[BASELINE] < counts[PRS]:
            team = BASELINE
        else:
            team = PRS if rng.random() < 0.5 else BASELINE
        order = lists[team]
        while cursors[team] < len(order) and order[cursors[team]] in used:
            cursors[team] += 1
        if cursors[team] >= len(order):  # this team ran out; the other finishes
            team = BASELINE if team == PRS else PRS
            order = lists[team]
            while cursors[team] < len(order) and order[cursors[team]] in used:
                cursors[team] += 1
            if cursors[team] >= len(order):
                break
        item = order[cursors[team]]
        used.add(item)
        picked.append((item, team))
        counts[team] += 1
    return picked


def baseline_order(rows: Sequence[tuple]) -> list[tuple]:
    """Newest first (published, else fetched), the plain-reader default."""

    def moment(row) -> datetime:
        item = row[0]
        value = getattr(item, "published_at", None) or getattr(item, "fetched_at", None)
        if value is None:
            return datetime.min.replace(tzinfo=UTC)
        return value if value.tzinfo else value.replace(tzinfo=UTC)

    return sorted(rows, key=moment, reverse=True)


def interleave_ranked(ranked: list[tuple], rng: random.Random) -> list[tuple]:
    """Re-order (item, prs, breakdown) rows by team draft and tag each row's team."""
    by_id = {row[0].id: row for row in ranked}
    drafted = team_draft(
        [row[0].id for row in ranked], [row[0].id for row in baseline_order(ranked)], rng
    )
    out: list[tuple] = []
    for item_id, team in drafted:
        item, prs, breakdown = by_id[item_id]
        breakdown["_team"] = team
        out.append((item, prs, breakdown))
    return out


def finished(interaction) -> bool:
    if interaction is None:
        return False
    return bool(
        (interaction.read_completion_pct or 0) >= FINISHED_COMPLETION
        or (interaction.explicit_rating or 0) > 0
        or interaction.saved
    )


def digest_outcome(teams: dict[uuid.UUID, str], interactions: dict[uuid.UUID, object]) -> str:
    """'prs', 'baseline' or 'tie' for one interleaved digest."""
    wins = Counter(team for item_id, team in teams.items() if finished(interactions.get(item_id)))
    if wins[PRS] > wins[BASELINE]:
        return PRS
    if wins[BASELINE] > wins[PRS]:
        return BASELINE
    return "tie"


async def interleaving_report(session, *, days: int = 7, now: datetime | None = None) -> dict:
    """Per-user and pooled PRS win rate over interleaved digests in the window."""
    from sqlalchemy import select

    from app.models.content import UserContentInteraction
    from app.models.digest import Digest, DigestImpression

    now = now or datetime.now(UTC)
    since = now - timedelta(days=days)
    rows = (
        await session.execute(
            select(
                Digest.id, Digest.user_id, DigestImpression.content_item_id, DigestImpression.team
            )
            .join(DigestImpression, DigestImpression.digest_id == Digest.id)
            .where(Digest.generated_at >= since, DigestImpression.team.isnot(None))
        )
    ).all()
    digests: dict[uuid.UUID, dict] = {}
    for digest_id, user_id, item_id, team in rows:
        digests.setdefault(digest_id, {"user": user_id, "teams": {}})["teams"][item_id] = team
    per_user: dict[uuid.UUID, Counter] = {}
    for info in digests.values():
        ids = list(info["teams"])
        interactions = {
            ix.content_item_id: ix
            for ix in (
                await session.execute(
                    select(UserContentInteraction).where(
                        UserContentInteraction.user_id == info["user"],
                        UserContentInteraction.content_item_id.in_(ids),
                    )
                )
            ).scalars()
        }
        per_user.setdefault(info["user"], Counter())[
            digest_outcome(info["teams"], interactions)
        ] += 1

    def summary(counter: Counter) -> dict:
        decided = counter[PRS] + counter[BASELINE]
        return {
            "prs_wins": counter[PRS],
            "baseline_wins": counter[BASELINE],
            "ties": counter["tie"],
            "prs_win_rate": round(counter[PRS] / decided, 3) if decided else None,
        }

    pooled = sum(per_user.values(), Counter())
    return {
        "window_days": days,
        "digests": len(digests),
        "pooled": summary(pooled),
        "users": {str(user): summary(counter) for user, counter in per_user.items()},
    }
