from __future__ import annotations

import hashlib
import math
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.content import ContentItem, UserContentInteraction
from app.models.digest import Digest, DigestFeedbackPrompt, DigestImpression, DigestItem
from app.models.user import User
from app.services.digest.sections import SectionBuilder
from app.services.ranking.engine import rank_content_for_user
from app.utils.logging import get_logger

logger = get_logger(__name__)

NEW_USER_THRESHOLD_DAYS = 14  # Use collaborative warmup for users younger than this

# Serendipity ("discovery") candidates should be interest-*adjacent* — near the
# edges of the user's interest clusters — not merely recent items from strangers'
# sources (audit 04-1). In pgvector cosine-distance terms (1 - cosine_similarity),
# we take items whose distance to the user's interest vector falls in a band that
# is related but outside the already-core region.
SERENDIPITY_MIN_DISTANCE = 0.35  # closer than this ≈ already core interest
SERENDIPITY_MAX_DISTANCE = 0.75  # farther than this ≈ unrelated noise


async def _select_serendipity_candidates(
    user: User,
    source_ids: list,
    cutoff: datetime,
    count: int,
    session: AsyncSession,
    *,
    feed_ids: list | None = None,
) -> list[ContentItem]:
    """Pick discovery candidates adjacent to the user's interests.

    Uses the user's aggregated interest vector and pgvector cosine distance to
    surface content near — but outside — their established clusters. Falls back
    to recent public content when the user has no interest vector yet (brand-new
    users), preserving day-1 behaviour.
    """
    from app.services.interest_graph.graph import InterestGraphManager
    from app.services.takedown import not_blocked_filter

    base_filters = [
        ContentItem.fetched_at >= cutoff,
        ContentItem.owner_user_id.is_(None),  # never surface others' private content
        not_blocked_filter(),
    ]
    if source_ids or feed_ids:
        from app.services.feed_identity import outside_user_feeds

        base_filters.append(outside_user_feeds(source_ids, feed_ids or []))

    interest_vec = await InterestGraphManager().build_user_interest_vector(user.id, session)
    if interest_vec is not None:
        vec = interest_vec.tolist()
        distance = ContentItem.embedding.cosine_distance(vec)
        result = await session.execute(
            select(ContentItem)
            .where(
                *base_filters,
                ContentItem.embedding.isnot(None),
                distance >= SERENDIPITY_MIN_DISTANCE,
                distance <= SERENDIPITY_MAX_DISTANCE,
            )
            .order_by(distance.asc())  # closest within the adjacent band first
            .limit(count)
        )
        candidates = list(result.scalars().all())
        if candidates:
            return candidates
        # No adjacent items in-window — fall through to the recency fallback.

    result = await session.execute(
        select(ContentItem)
        .where(*base_filters)
        .order_by(ContentItem.fetched_at.desc())
        .limit(count)
    )
    return list(result.scalars().all())


# Quiet day (#142): when the user's feeds produced nothing new in the window,
# catch up on unread items from their own feeds instead of an empty digest.
QUIET_FALLBACK_WINDOW = timedelta(days=14)
QUIET_FALLBACK_LABEL = "Your sources were quiet: catching up from the last two weeks"


async def _quiet_day_fallback(
    user: User, source_ids: list, feed_ids: list, session: AsyncSession
) -> list[ContentItem]:
    """Unread, never-digested items from the user's own feeds, newest first."""
    from app.services.feed_identity import from_user_feeds, visible_item_filter

    already_digested = (
        select(DigestItem.content_item_id)
        .join(Digest, Digest.id == DigestItem.digest_id)
        .where(Digest.user_id == user.id)
    )
    from app.services.takedown import not_blocked_filter

    opened = select(UserContentInteraction.content_item_id).where(
        UserContentInteraction.user_id == user.id,
        UserContentInteraction.opened_at.isnot(None),
    )
    result = await session.execute(
        select(ContentItem)
        .where(
            from_user_feeds(source_ids, feed_ids),
            ContentItem.fetched_at >= datetime.now(UTC) - QUIET_FALLBACK_WINDOW,
            visible_item_filter(user.id),
            not_blocked_filter(),
            ContentItem.id.notin_(already_digested),
            ContentItem.id.notin_(opened),
        )
        .order_by(ContentItem.fetched_at.desc())
        .limit(120)
    )
    return [item for item in result.scalars().all() if item.rankable]


async def _candidates(
    user: User, source_ids: list, feed_ids: list, cutoff: datetime, session: AsyncSession
) -> list[ContentItem]:
    """The items a digest build ranks (#313): the newest rankable items in the
    window, at most DIGEST_PER_SOURCE_CAP per feed, up to DIGEST_CANDIDATE_LIMIT,
    newest first. Without an ORDER BY the old LIMIT 200 handed the ranker an
    arbitrary subset, and every feed past it never competed."""
    from app.services.feed_identity import from_user_feeds, visible_item_filter
    from app.services.takedown import not_blocked_filter

    settings_ = get_settings()
    cap = settings_.digest_per_source_cap
    newest_per_feed = (
        select(
            ContentItem.id,
            func.row_number()
            .over(
                partition_by=func.coalesce(ContentItem.feed_id, ContentItem.source_id),
                order_by=ContentItem.fetched_at.desc(),
            )
            .label("rn"),
        )
        .where(
            from_user_feeds(source_ids, feed_ids),
            ContentItem.fetched_at >= cutoff,
            visible_item_filter(user.id),
            not_blocked_filter(),
            ContentItem.rankable.is_(True),
        )
        .subquery()
    )
    result = await session.execute(
        select(ContentItem)
        .join(newest_per_feed, newest_per_feed.c.id == ContentItem.id)
        .where(newest_per_feed.c.rn <= cap if cap > 0 else true())
        .order_by(ContentItem.fetched_at.desc(), ContentItem.id)
        .limit(settings_.digest_candidate_limit)
    )
    return list(result.scalars().all())


async def summarize_placed(
    user: User, items: list[ContentItem], session: AsyncSession | None = None
) -> int:
    """LLM summaries for a digest's items, within the plan's daily allowance (#172).

    A reader's own key (#255) is used instead when they have one, and those
    summaries don't count against the allowance.
    """
    from app.services import entitlements
    from app.services.llm.user_keys import summarizer_for
    from app.services.summarization.lazy import ensure_llm_summaries

    limit = get_settings().digest_llm_summary_limit
    own = await summarizer_for(session, user.id) if session is not None else None
    if own is not None:
        return await ensure_llm_summaries(items, limit=limit, summarizer=own)
    left = await entitlements.remaining_today(user, entitlements.LLM_SUMMARIES)
    if left is not None:
        limit = min(limit, left)
    calls = await ensure_llm_summaries(items, limit=limit)
    await entitlements.record_use(user, entitlements.LLM_SUMMARIES, calls)
    return calls


async def build_digest(user: User, session: AsyncSession) -> Digest:
    # Determine time window
    if user.digest_frequency == "weekly":
        cutoff = datetime.now(UTC) - timedelta(days=7)
    else:
        cutoff = datetime.now(UTC) - timedelta(hours=24)

    # Sources sharing a feed with any of the user's active sources (#108): a
    # public item is stored once, under whichever subscriber's source ingested
    # it first, so filtering by the user's own source ids missed it.
    from app.services.feed_identity import (
        equivalent_source_ids,
        user_feed_ids,
    )

    source_ids = await equivalent_source_ids(session, user.id)
    feed_ids = await user_feed_ids(session, user.id)

    if source_ids or feed_ids:
        content_items = await _candidates(user, source_ids, feed_ids, cutoff, session)
    else:
        content_items = []

    # Per-user language filter (UX-15): empty prefs = no filter; items with
    # unknown language are never dropped (the filter is for what you DO want).
    wanted_langs = [str(lang).lower() for lang in (user.preferred_languages or [])]
    if wanted_langs:
        content_items = [
            item
            for item in content_items
            if item.language is None or str(item.language).lower() in wanted_langs
        ]

    from app.services.ingestion.backfill import cap_per_source

    content_items = cap_per_source(content_items, get_settings().digest_per_source_cap)

    quiet_fallback_ids: set = set()
    if not content_items and (source_ids or feed_ids):
        fallback = await _quiet_day_fallback(user, source_ids, feed_ids, session)
        if wanted_langs:
            fallback = [
                item
                for item in fallback
                if item.language is None or str(item.language).lower() in wanted_langs
            ]
        content_items = cap_per_source(fallback, get_settings().digest_per_source_cap)
        quiet_fallback_ids = {item.id for item in content_items}
        if content_items:
            logger.info(f"Quiet day for {user.id}: {len(content_items)} catch-up items")

    # Serendipity candidates: interest-adjacent discovery, not recent-random.
    serendipity_count = max(5, math.ceil(len(content_items) * 0.10))
    serendipity_items = await _select_serendipity_candidates(
        user, source_ids, cutoff, serendipity_count, session, feed_ids=feed_ids
    )

    # Collaborative warmup for new users
    user_age_days = (datetime.now(UTC) - user.created_at.replace(tzinfo=UTC)).days
    if user_age_days < NEW_USER_THRESHOLD_DAYS and len(content_items) < 10:
        try:
            from app.services.cold_start.collaborative import get_collaborative_warmup_items

            warmup_items = await get_collaborative_warmup_items(user, limit=10, session=session)
            existing_ids = {item.id for item in content_items}
            for w in warmup_items:
                if w.id not in existing_ids:
                    content_items.append(w)
                    existing_ids.add(w.id)
            logger.info(
                f"Added {len(warmup_items)} collaborative warmup items for new user {user.id}"
            )
        except Exception as e:
            logger.warning(f"Collaborative warmup failed (non-fatal): {e}")

    all_items = content_items + serendipity_items
    if not all_items:
        logger.warning(f"No content items found for user {user.id} digest")

    # Mark serendipity items in interactions table
    for item in serendipity_items:
        await _ensure_interaction(user.id, item.id, was_suggested=True, session=session)

    # Cross-source topic synthesis: detect near-duplicate stories, synthesize
    all_items, story_payloads = await _synthesize_topic_clusters(all_items, session)

    # Rank all items
    limit = max(user.digest_max_items * 3, 60)
    ranked = await rank_content_for_user(user, all_items, session, limit=limit)
    ranked = diversify_ranked(ranked)
    if get_settings().ranking_interleaving:
        from random import Random

        from app.services.ranking.interleaving import interleave_ranked

        ranked = interleave_ranked(ranked, Random(f"interleave:{user.id}:{uuid.uuid4()}"))

    # The serendipity picks ARE the discovery section candidates (A6):
    # label them explicitly and make sure they survived the rank cutoff.
    serendipity_ids = {item.id for item in serendipity_items}
    ranked_ids = {item.id for item, _, _ in ranked}
    for item, _prs, breakdown in ranked:
        if item.id in serendipity_ids:
            breakdown["_serendipity_candidate"] = True
    for item in serendipity_items:
        if item.id not in ranked_ids:
            ranked.append((item, 0.0, {"_serendipity_candidate": True}))

    # Build sections
    builder = SectionBuilder(
        total_items=user.digest_max_items,
        serendipity_pct=user.serendipity_percentage,
    )
    sections = builder.build(ranked)

    # Exploration slots (A6): sampled from digest positions 6-40 with softmax
    # propensity, behind RANKING_EXPLORATION_ENABLED. Applied after layout so
    # every exploration pick is a placed item; positions < 6 never lead anyway.
    # Freshly seeded per build so successive builds explore different slots;
    # the drawn propensity is logged on each impression for later IPW.
    from random import Random

    from app.services.ranking.learning import exploration_plan

    placed: list[tuple] = []
    for section in sections.values():
        for row in section.items:
            placed.append(row)
    # New users (first 14 days) explore even when the global flag is off
    # (CS-04): exploration is how a population-free instance learns what the
    # digest slots the user has never clicked actually mean.
    exploration_on = (
        get_settings().ranking_exploration_enabled or user_age_days < NEW_USER_THRESHOLD_DAYS
    )
    if exploration_on and len(placed) >= 6:
        rng = Random(f"explore:{user.id}:{uuid.uuid4()}")
        plan_by_index = {
            row["index"]: row for row in exploration_plan([row[1] for row in placed], rng=rng)
        }
        for index, plan_row in plan_by_index.items():
            if index < len(placed):
                breakdown = placed[index][2]
                breakdown["exploration"] = True
                breakdown["_propensity"] = plan_row["propensity"]

    # Auto-learn digest length and serendipity from engagement history
    await _adjust_digest_preferences(user, session)

    # Create digest record
    section_counts = {name: len(sec.items) for name, sec in sections.items()}
    total = sum(section_counts.values())

    digest = Digest(
        user_id=user.id,
        generated_at=datetime.now(UTC),
        delivery_method="in_app",
        section_counts=section_counts,
        total_items=total,
    )
    session.add(digest)
    await session.flush()

    # Model summaries only for what the user will actually see (#147).
    await summarize_placed(
        user, [row[0] for section in sections.values() for row in section.items], session
    )

    # The ranker already produced each item's features, faithful contributions,
    # explanation and topic phrase from the same computation that scored it
    # (#129, #143); the digest stores them as they are.
    from app.services.ranking.contract import SIGNALS
    from app.services.ranking.learning import RANKER_VERSION

    position = 0
    for section_name, section in sections.items():
        for item, prs, breakdown in section.items:
            clean_breakdown = {k: v for k, v in breakdown.items() if not k.startswith("_")}
            if getattr(item, "discovered_via", None):
                clean_breakdown["discovered_via"] = item.discovered_via
            if item.id in quiet_fallback_ids:
                clean_breakdown["fallback_reason"] = QUIET_FALLBACK_LABEL
            numeric = {
                key: float(value)
                for key, value in clean_breakdown.items()
                if key in SIGNALS and isinstance(value, int | float)
            }
            story = story_payloads.get(item.id)
            if story:
                clean_breakdown["perspectives"] = story["perspectives"]
                if story.get("story_briefing"):
                    clean_breakdown["story_briefing"] = story["story_briefing"]
            di = DigestItem(
                digest_id=digest.id,
                content_item_id=item.id,
                position=position,
                section=section_name,
                prs_score=prs,
                signal_breakdown=clean_breakdown,
            )
            session.add(di)
            session.add(
                DigestImpression(
                    user_id=user.id,
                    content_item_id=item.id,
                    digest_id=digest.id,
                    section=section_name,
                    position=position,
                    score=float(prs),
                    features_json=numeric,
                    weights_version=RANKER_VERSION,
                    exploration=bool(clean_breakdown.get("exploration")),
                    propensity=float(breakdown.get("_propensity", 1.0)),
                    team=breakdown.get("_team"),
                )
            )
            position += 1

            # Update interaction to mark as surfaced in digest
            await _mark_surfaced_in_digest(user.id, item.id, prs, session)

    await session.flush()

    # For new users (first 14 days): generate conversational feedback prompts
    if user_age_days < NEW_USER_THRESHOLD_DAYS and total > 0:
        await _generate_feedback_prompts(digest, sections, user_age_days, session)
        await session.flush()

    logger.info(f"Built digest {digest.id} for user {user.id}: {total} items")
    return digest


def diversify_ranked(ranked: list[tuple]) -> list[tuple]:
    """MMR re-rank of the scored candidates before section layout (#148).

    Trades a little score for variety (lambda 0.7), drops near-duplicates
    (cosine >= 0.92) that story clustering missed, and caps any one topic at
    30% of the candidates. No "novelty share" swap-ins here: exploration
    slots already do that, with logged propensities.
    """
    import numpy as np

    from app.services.ranking.interests import diversify

    if len(ranked) < 3:
        return ranked
    vectors = []
    for item, _, _ in ranked:
        raw = getattr(item, "embedding", None)
        vec = None if raw is None else np.asarray(raw, dtype=np.float32)
        vectors.append(vec if vec is not None and float(np.linalg.norm(vec)) > 1e-8 else None)
    return diversify(
        ranked,
        scores=[float(prs) for _, prs, _ in ranked],
        vectors=vectors,
        clusters=[(item.topic_clusters or [None])[0] for item, _, _ in ranked],
        lam=0.7,
        cluster_cap=0.3,
        novelty_share=0.0,
        near_dup=0.92,
    )


async def _synthesize_topic_clusters(
    items: list[ContentItem],
    session: AsyncSession,
) -> tuple[list[ContentItem], dict[uuid.UUID, dict]]:
    """
    UX-09: cluster same-story items (embedding cosine, title-token overlap for
    no-embedding pairs), keep one primary card per story and attach the other
    sources as `perspectives`. LLM briefing is cached; without one the
    perspectives list is the fallback rendering.

    Returns (kept_items, {primary_id: {"perspectives": [...], "story_briefing": str|None}}).
    The stored `summary_brief` on the (shared) content row is never touched:
    a cluster briefing would otherwise leak into other users' digests and
    poison the synthesis cache key on later builds (CodeRabbit).
    """
    if len(items) < 2:
        return items, {}

    from app.services.digest.synthesis import cluster_stories

    clusters = cluster_stories(items)

    kept_items: list[ContentItem] = []
    story_payloads: dict[uuid.UUID, dict] = {}
    dropped = 0

    for cluster in clusters:
        primary = items[cluster[0]]
        kept_items.append(primary)
        if len(cluster) < 2:
            continue

        story_payloads[primary.id] = {
            "perspectives": [
                {
                    "title": items[idx].title,
                    "url": items[idx].url,
                    "source_id": str(items[idx].source_id) if items[idx].source_id else None,
                }
                for idx in cluster[1:]
            ],
            "story_briefing": None,
        }
        dropped += len(cluster) - 1

        # Cached LLM briefing (optional polish — the card ships either way).
        briefs = "\n\n".join(
            f"- {items[idx].summary_brief or items[idx].title}" for idx in cluster[:5]
        )
        cache_key = f"synth:{hashlib.sha256(briefs.encode()).hexdigest()[:32]}"
        try:
            from app.utils.cache import cache_get, cache_set

            synthesized = await cache_get(cache_key)
            if synthesized is None:
                from app.services.summarization.groq_client import LLMSummarizer
                from app.services.summarization.groq_client import SummarizationResult as SR

                summarizer = LLMSummarizer()
                pseudo_results = [
                    SR(
                        headline=items[idx].summary_headline or items[idx].title,
                        brief=items[idx].summary_brief or "",
                        detailed=items[idx].summary_detailed or "",
                        depth_score=items[idx].content_depth_score or 0.5,
                        is_original_reporting=items[idx].is_original_reporting or False,
                        has_citations=items[idx].has_citations,
                        topic_clusters=items[idx].topic_clusters or [],
                        reading_time_minutes=items[idx].reading_time_minutes or 5,
                    )
                    for idx in cluster[:5]
                ]
                topic_label = (primary.topic_clusters or [primary.title])[0]
                synthesized = await summarizer.synthesize_topic(pseudo_results, topic_label)
                if synthesized:
                    await cache_set(cache_key, synthesized, ttl_seconds=7 * 24 * 3600)
            story_payloads[primary.id]["story_briefing"] = synthesized or None
        except Exception as e:
            logger.debug(f"Synthesis failed (non-fatal): {e}")

    if dropped > 0:
        logger.info(f"Story synthesis folded {dropped} same-story items into cards")
    await session.flush()
    return kept_items, story_payloads


async def _ensure_interaction(
    user_id: uuid.UUID,
    content_item_id: uuid.UUID,
    was_suggested: bool,
    session: AsyncSession,
) -> None:
    result = await session.execute(
        select(UserContentInteraction).where(
            UserContentInteraction.user_id == user_id,
            UserContentInteraction.content_item_id == content_item_id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing is None:
        interaction = UserContentInteraction(
            user_id=user_id,
            content_item_id=content_item_id,
            was_suggested=was_suggested,
        )
        session.add(interaction)
        await session.flush()


async def _mark_surfaced_in_digest(
    user_id: uuid.UUID,
    content_item_id: uuid.UUID,
    prs: float,
    session: AsyncSession,
) -> None:
    result = await session.execute(
        select(UserContentInteraction).where(
            UserContentInteraction.user_id == user_id,
            UserContentInteraction.content_item_id == content_item_id,
        )
    )
    interaction = result.scalar_one_or_none()
    if interaction:
        interaction.surfaced_in_digest = True
        interaction.prs_score = prs
    else:
        interaction = UserContentInteraction(
            user_id=user_id,
            content_item_id=content_item_id,
            surfaced_in_digest=True,
            prs_score=prs,
        )
        session.add(interaction)
    await session.flush()


_EARLY_PROMPTS: list[dict] = [
    {
        "type": "depth_level",
        "text": "Was today's content the right depth — or would you prefer more in-depth analysis?",
    },
    {
        "type": "topic_accuracy",
        "text": "Did today's digest match your interests, or did anything feel off-topic?",
    },
    {
        "type": "source_quality",
        "text": "Were the sources today high quality and trustworthy for you?",
    },
    {"type": "depth_level", "text": "Were the articles too long, too short, or just right?"},
    {"type": "topic_accuracy", "text": "Was there a topic today you'd like to see more of?"},
    {
        "type": "source_quality",
        "text": "Did you discover any new sources today that you'd like to follow?",
    },
]


async def _generate_feedback_prompts(
    digest: Digest,
    sections: dict,
    user_age_days: int,
    session: AsyncSession,
) -> None:
    """
    For users in their first 14 days, attach 2–3 targeted conversational prompts per digest.
    Rotates through _EARLY_PROMPTS based on digest count so questions vary each day.
    """
    # Count existing prompts for this user's digests to pick the next in rotation
    from sqlalchemy import func as sa_func

    prompt_count_result = await session.execute(
        select(sa_func.count(DigestFeedbackPrompt.id))
        .join(Digest, DigestFeedbackPrompt.digest_id == Digest.id)
        .where(Digest.user_id == digest.user_id)
    )
    existing_count = prompt_count_result.scalar() or 0

    # Dismissal must stick across digests (UX-07): a prompt type the user
    # dismissed once never rotates back in (CodeRabbit).
    dismissed_result = await session.execute(
        select(DigestFeedbackPrompt.prompt_type)
        .join(Digest, DigestFeedbackPrompt.digest_id == Digest.id)
        .where(Digest.user_id == digest.user_id, DigestFeedbackPrompt.dismissed.is_(True))
    )
    dismissed_types = {row[0] for row in dismissed_result.all()}
    pool = [p for p in _EARLY_PROMPTS if p["type"] not in dismissed_types]
    if not pool:
        return  # everything dismissed — stop prompting entirely

    num_prompts = 3 if user_age_days < 7 else 2
    # Pick a content item from the first section to anchor one of the prompts
    anchor_item_id = None
    for section in sections.values():
        if section.items:
            anchor_item_id = section.items[0][0].id  # (content, prs, breakdown)[0].id
            break

    for i in range(num_prompts):
        prompt_def = pool[(existing_count + i) % len(pool)]
        prompt = DigestFeedbackPrompt(
            digest_id=digest.id,
            content_item_id=anchor_item_id if i == 0 else None,
            prompt_text=prompt_def["text"],
            prompt_type=prompt_def["type"],
        )
        session.add(prompt)


async def _adjust_digest_preferences(user: User, session: AsyncSession) -> None:
    """
    Auto-learn digest length from engagement history and serendipity level
    from topical diversity. Writes back to user row if adjustments are made.
    """
    try:
        await _learn_digest_length(user, session)

        # Measure topical diversity over last 14 days for serendipity adjustment
        diversity_cutoff = datetime.now(UTC) - timedelta(days=14)
        from sqlalchemy import text as sql_text

        div_result = await session.execute(
            sql_text(
                """
                SELECT COUNT(DISTINCT topic) as topic_count, COUNT(*) as total
                FROM (
                    SELECT jsonb_array_elements_text(ci.topic_clusters) as topic
                    FROM content_items ci
                    JOIN user_content_interactions uci ON ci.id = uci.content_item_id
                    WHERE uci.user_id = :uid
                      AND uci.created_at >= :cutoff
                      AND uci.read_completion_pct >= 0.5
                ) t
            """
            ),
            {"uid": str(user.id), "cutoff": diversity_cutoff},
        )
        div_row = div_result.fetchone()
        if div_row and div_row[1] > 10:
            diversity_ratio = div_row[0] / max(1, div_row[1])
            # Narrow focus (low diversity) → boost serendipity; broad → reduce slightly
            if diversity_ratio < 0.3 and user.serendipity_percentage < 25:
                user.serendipity_percentage = min(25, user.serendipity_percentage + 3)
                logger.info(
                    f"Increased serendipity to {user.serendipity_percentage}% for user {user.id}"
                )
            elif diversity_ratio > 0.6 and user.serendipity_percentage > 10:
                user.serendipity_percentage = max(10, user.serendipity_percentage - 2)

        await session.flush()
    except Exception as e:
        logger.warning(f"digest preference adjustment failed (non-fatal): {e}")


async def _learn_digest_length(user: User, session: AsyncSession) -> None:
    """UX-02: N = clamp(1.25 · EMA(opened per digest), 5, 30) unless locked.

    Runs before the current digest row is created, so the window only covers
    past digests. The learned length applies to the next build.
    """
    from app.services.digest.length import EMA_WINDOW, ema_opened_per_digest, target_digest_length

    if user.digest_length_locked:
        return

    digests_result = await session.execute(
        select(Digest.id)
        .where(Digest.user_id == user.id)
        .order_by(Digest.generated_at.desc())
        .limit(EMA_WINDOW)
    )
    digest_ids = [row[0] for row in digests_result.all()]
    if not digest_ids:
        return

    from sqlalchemy import and_

    opened_result = await session.execute(
        select(DigestImpression.digest_id, func.count(func.distinct(UserContentInteraction.id)))
        .join(
            UserContentInteraction,
            and_(
                UserContentInteraction.user_id == user.id,
                UserContentInteraction.content_item_id == DigestImpression.content_item_id,
                UserContentInteraction.opened_at.isnot(None),
            ),
        )
        .where(DigestImpression.digest_id.in_(digest_ids))
        .group_by(DigestImpression.digest_id)
    )
    opened_by_digest = {row[0]: int(row[1]) for row in opened_result.all()}

    # oldest → newest, matching the EMA's direction
    ordered_counts = [
        float(opened_by_digest.get(digest_id, 0)) for digest_id in reversed(digest_ids)
    ]
    ema = ema_opened_per_digest(ordered_counts)
    target = target_digest_length(ema, current=user.digest_max_items, locked=False)
    if target != user.digest_max_items:
        user.digest_max_items = target
        logger.info(f"Auto-adjusted digest length to {target} for user {user.id}")
