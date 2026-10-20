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
    """Pooled PRS win rate and the spread of per-user rates, in the window."""
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
    # No user ids in operator output (#224): the spread of per-user win rates
    # is what the evaluation needs, not who they belong to.
    rates = sorted(
        rate for rate in (summary(c)["prs_win_rate"] for c in per_user.values()) if rate is not None
    )
    return {
        "window_days": days,
        "digests": len(digests),
        "pooled": summary(pooled),
        "users": len(per_user),
        "user_win_rates": rates,
    }


async def user_comparison(
    session,
    user_id: uuid.UUID,
    *,
    days: int = 7,
    now: datetime | None = None,
    min_examples: int = 1,
) -> dict:
    """'Your digest vs newest-first' for ONE user (#237); never other users' data.

    Examples: articles the reader finished in the last `days` days that PRS
    placed near the top while newest-first, over the same digest, would have
    buried. If interleaved digests exist, also the reader's own outcomes.
    """
    from sqlalchemy import select

    from app.models.content import ContentItem, UserContentInteraction
    from app.models.digest import Digest, DigestImpression, DigestItem
    from app.models.user import User

    now = now or datetime.now(UTC)
    user = await session.get(User, user_id)
    created = user.created_at if user else None
    if created is not None and created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    if user is None or created is None or now - created < timedelta(days=7):
        return {"available": False, "reason": "too_new", "examples": [], "interleaving": None}

    since = now - timedelta(days=days)
    rows = (
        await session.execute(
            select(Digest.id, Digest.generated_at, DigestItem.position, ContentItem)
            .join(DigestItem, DigestItem.digest_id == Digest.id)
            .join(ContentItem, ContentItem.id == DigestItem.content_item_id)
            .where(Digest.user_id == user_id, Digest.generated_at >= since)
        )
    ).all()
    finished_ids = {
        ix.content_item_id
        for ix in (
            await session.execute(
                select(UserContentInteraction).where(
                    UserContentInteraction.user_id == user_id,
                    UserContentInteraction.content_item_id.in_(
                        {row[3].id for row in rows} or {uuid.uuid4()}
                    ),
                )
            )
        ).scalars()
        if finished(ix)
    }
    by_digest: dict[uuid.UUID, list] = {}
    for digest_id, generated_at, position, item in rows:
        by_digest.setdefault(digest_id, []).append((generated_at, position, item))

    examples = []
    for entries in by_digest.values():
        newest = sorted(entries, key=lambda e: e[2].fetched_at or e[0], reverse=True)
        newest_rank = {e[2].id: i + 1 for i, e in enumerate(newest)}
        for generated_at, position, item in entries:
            ours, theirs = position + 1, newest_rank[item.id]
            if item.id in finished_ids and theirs - ours >= 5:
                examples.append(
                    {
                        "content_id": str(item.id),
                        "title": item.title,
                        "digest_date": generated_at.date().isoformat(),
                        "your_position": ours,
                        "newest_first_position": theirs,
                    }
                )
    examples.sort(key=lambda e: e["newest_first_position"] - e["your_position"], reverse=True)

    interleaved = (
        await session.execute(
            select(
                DigestImpression.digest_id, DigestImpression.content_item_id, DigestImpression.team
            )
            .join(Digest, Digest.id == DigestImpression.digest_id)
            .where(
                Digest.user_id == user_id,
                Digest.generated_at >= since,
                DigestImpression.team.isnot(None),
            )
        )
    ).all()
    outcome = None
    if interleaved:
        teams: dict[uuid.UUID, dict] = {}
        for digest_id, item_id, team in interleaved:
            teams.setdefault(digest_id, {})[item_id] = team
        interactions = {
            ix.content_item_id: ix
            for ix in (
                await session.execute(
                    select(UserContentInteraction).where(UserContentInteraction.user_id == user_id)
                )
            ).scalars()
        }
        counts = Counter(digest_outcome(t, interactions) for t in teams.values())
        outcome = {
            "digests": len(teams),
            "prs_wins": counts[PRS],
            "newest_wins": counts[BASELINE],
            "ties": counts["tie"],
        }

    available = len(examples) >= min_examples
    return {
        "available": available,
        "reason": None if available else "not_enough_reading",
        "window_days": days,
        "examples": examples[:3],
        "interleaving": outcome,
    }
