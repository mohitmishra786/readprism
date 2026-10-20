"""GDPR/CCPA account data export + erasure (audit 06-3).

Weirling stores email, reading telemetry, an interest graph, learned weights
and interaction history — behavioural personal data. EU/California users have a
right to a portable copy of it (Art. 20 / CCPA) and to erasure (Art. 17). These
helpers back the `/account/export` and `DELETE /account` endpoints.

Erasure relies on the `ondelete="CASCADE"` foreign keys already declared on every
user-owned table, so deleting the `users` row removes sources, creators,
interactions, interest nodes/edges, meta-weights, creator trust and digests in
one DB-enforced sweep. Shared `content_items` (deduped across all users by URL)
are intentionally *not* deleted — they are not the user's personal data; the FK
from those rows to the user's sources is `SET NULL`, not cascade.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem, UserContentInteraction
from app.models.creator import Creator, CreatorPlatform
from app.models.creator_trust import CreatorTopicTrust
from app.models.digest import Digest, DigestItem
from app.models.interest_graph import InterestEdge, InterestNode
from app.models.meta_weights import UserMetaWeights
from app.models.product_event import ProductEvent
from app.models.source import Source
from app.models.user import User
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Columns never included in an export: opaque derived vectors (not human-portable)
# and the password hash (a secret, not personal data the user needs back).
_EXCLUDED_COLUMNS = {"embedding", "topic_embedding", "hashed_password"}


# Article metadata exported for items you were shown or touched (format 2,
# #200): enough to know what each digest offered and to replay rankings
# offline. Publisher full text is not included.
_CONTENT_COLUMNS = (
    "id",
    "url",
    "title",
    "author",
    "summary_brief",
    "topic_clusters",
    "source_id",
    "feed_id",
    "origin",
    "published_at",
    "fetched_at",
    "word_count",
    "reading_time_minutes",
    "has_citations",
    "content_depth_score",
    "is_original_reporting",
    "rankable",
)


def _content_dict(item: ContentItem) -> dict[str, Any]:
    full = _row_to_dict(item)
    return {name: full.get(name) for name in _CONTENT_COLUMNS}


def _row_to_dict(obj: Any) -> dict[str, Any]:
    """Serialize a SQLAlchemy model instance to a JSON-friendly dict."""
    result: dict[str, Any] = {}
    for column in obj.__table__.columns:
        name = column.name
        if name in _EXCLUDED_COLUMNS:
            continue
        value = getattr(obj, name)
        if isinstance(value, datetime | date | time):
            value = value.isoformat()
        elif isinstance(value, uuid.UUID):
            value = str(value)
        result[name] = value
    return result


async def _all(session: AsyncSession, stmt) -> list[dict[str, Any]]:
    result = await session.execute(stmt)
    exported: list[dict[str, Any]] = []
    item: Any
    for item in result.scalars().all():
        exported.append(_row_to_dict(item))
    return exported


async def export_user_data(session: AsyncSession, user: User) -> dict[str, Any]:
    """Return a complete, portable JSON bundle of everything tied to `user`."""
    uid = user.id

    creators = (
        (await session.execute(select(Creator).where(Creator.user_id == uid))).scalars().all()
    )
    creator_ids = [c.id for c in creators]
    creator_platforms: list[dict[str, Any]] = []
    if creator_ids:
        creator_platforms = await _all(
            session,
            select(CreatorPlatform).where(CreatorPlatform.creator_id.in_(creator_ids)),
        )

    from app.services.feed_identity import visible_item_filter

    digest_items = await _all(
        session,
        select(DigestItem)
        .join(Digest, Digest.id == DigestItem.digest_id)
        .where(Digest.user_id == uid)
        .order_by(DigestItem.digest_id, DigestItem.position),
    )
    touched = select(UserContentInteraction.content_item_id).where(
        UserContentInteraction.user_id == uid
    )
    shown = (
        select(DigestItem.content_item_id)
        .join(Digest, Digest.id == DigestItem.digest_id)
        .where(Digest.user_id == uid)
    )
    content = [
        _content_dict(item)
        for item in (
            await session.execute(
                select(ContentItem).where(
                    ContentItem.id.in_(touched.union(shown)), visible_item_filter(uid)
                )
            )
        )
        .scalars()
        .all()
    ]

    return {
        "export_metadata": {
            "generated_at": datetime.now(UTC).isoformat(),
            # 2 (#200): adds digest_items and content metadata; additive.
            "format_version": 2,
            "note": (
                "Portable copy of your Weirling personal data (GDPR Art. 20 / CCPA). "
                "Derived embedding vectors and your password hash are excluded."
            ),
        },
        "profile": _row_to_dict(user),
        "sources": await _all(session, select(Source).where(Source.user_id == uid)),
        "creators": [_row_to_dict(c) for c in creators],
        "creator_platforms": creator_platforms,
        "interactions": await _all(
            session, select(UserContentInteraction).where(UserContentInteraction.user_id == uid)
        ),
        "interest_nodes": await _all(
            session, select(InterestNode).where(InterestNode.user_id == uid)
        ),
        "interest_edges": await _all(
            session, select(InterestEdge).where(InterestEdge.user_id == uid)
        ),
        "creator_topic_trust": await _all(
            session, select(CreatorTopicTrust).where(CreatorTopicTrust.user_id == uid)
        ),
        "meta_weights": await _all(
            session, select(UserMetaWeights).where(UserMetaWeights.user_id == uid)
        ),
        "digests": await _all(session, select(Digest).where(Digest.user_id == uid)),
        # First-party product events (#131), disclosed in PRIVACY.md.
        "product_events": await _all(
            session, select(ProductEvent).where(ProductEvent.user_id == uid)
        ),
        "digest_items": digest_items,
        "content": content,
    }


async def delete_user_account(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Irreversibly delete a user and all their personal data.

    The final `DELETE FROM users` cascades to every user-owned table via the
    DB-level foreign keys.
    """
    # DigestItems cascade from Digest; Digests cascade from User. But delete
    # explicitly is unnecessary — the DB handles it.
    await session.execute(
        delete(DigestItem).where(
            DigestItem.digest_id.in_(select(Digest.id).where(Digest.user_id == user_id))
        )
    )
    await session.execute(delete(User).where(User.id == user_id))
    await session.flush()
    logger.info(f"Deleted account and all personal data for user {user_id}")

    # Best-effort: purge per-user Redis caches so nothing lingers post-erasure.
    try:
        from app.utils.cache import get_redis

        redis = get_redis()
        keys = await redis.keys(f"*{user_id}*")
        if keys:
            await redis.delete(*keys)
    except Exception as e:  # pragma: no cover - cache purge is best-effort
        logger.warning(f"Post-deletion cache purge failed for {user_id}: {e}")
