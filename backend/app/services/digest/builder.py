from __future__ import annotations

import math
import uuid
from collections import defaultdict
from datetime import datetime, timezone, timedelta

import numpy as np
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem, UserContentInteraction
from app.models.digest import Digest, DigestFeedbackPrompt, DigestItem
from app.models.source import Source
from app.models.user import User
from app.services.digest.sections import SectionBuilder
from app.services.ranking.engine import rank_content_for_user
from app.utils.logging import get_logger

logger = get_logger(__name__)

NEW_USER_THRESHOLD_DAYS = 14  # Use collaborative warmup for users younger than this


async def build_digest(user: User, session: AsyncSession) -> Digest:
    # Determine time window
    if user.digest_frequency == "weekly":
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    else:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    # Get user's active sources
    sources_result = await session.execute(
        select(Source).where(Source.user_id == user.id, Source.is_active == True)
    )
    sources = list(sources_result.scalars().all())
    source_ids = [s.id for s in sources]

    # Fetch content items from user's sources
    if source_ids:
        content_result = await session.execute(
            select(ContentItem).where(
                ContentItem.source_id.in_(source_ids),
                ContentItem.fetched_at >= cutoff,
            ).limit(200)
        )
        content_items = list(content_result.scalars().all())
    else:
        content_items = []

    # Serendipity candidates: fetch extra from all recent content not in user sources
    serendipity_count = max(5, math.ceil(len(content_items) * 0.10))
    seen_source_ids_strs = {str(sid) for sid in source_ids}

    serendipity_result = await session.execute(
        select(ContentItem)
        .where(
            ContentItem.fetched_at >= cutoff,
            ContentItem.source_id.notin_(source_ids) if source_ids else True,
        )
        .order_by(ContentItem.fetched_at.desc())
        .limit(serendipity_count)
    )
    serendipity_items = list(serendipity_result.scalars().all())

    # Collaborative warmup for new users
    user_age_days = (datetime.now(timezone.utc) - user.created_at.replace(tzinfo=timezone.utc)).days
    if user_age_days < NEW_USER_THRESHOLD_DAYS and len(content_items) < 10:
        try:
            from app.services.cold_start.collaborative import get_collaborative_warmup_items
            warmup_items = await get_collaborative_warmup_items(user, limit=10, session=session)
            existing_ids = {item.id for item in content_items}
            for w in warmup_items:
                if w.id not in existing_ids:
                    content_items.append(w)
                    existing_ids.add(w.id)
            logger.info(f"Added {len(warmup_items)} collaborative warmup items for new user {user.id}")
        except Exception as e:
            logger.warning(f"Collaborative warmup failed (non-fatal): {e}")

    all_items = content_items + serendipity_items
    if not all_items:
        logger.warning(f"No content items found for user {user.id} digest")

    # Mark serendipity items in interactions table
    for item in serendipity_items:
        await _ensure_interaction(user.id, item.id, was_suggested=True, session=session)

    # Cross-source topic synthesis: detect near-duplicate stories, synthesize
    all_items = await _synthesize_topic_clusters(all_items, session)

    # Rank all items
    limit = max(user.digest_max_items * 3, 60)
    ranked = await rank_content_for_user(user, all_items, session, limit=limit)

    # Build sections
    builder = SectionBuilder(
        total_items=user.digest_max_items,
        serendipity_pct=user.serendipity_percentage,
    )
    sections = builder.build(ranked)

    # Auto-learn digest length and serendipity from engagement history
    await _adjust_digest_preferences(user, session)

    # Create digest record
    section_counts = {name: len(sec.items) for name, sec in sections.items()}
    total = sum(section_counts.values())

    digest = Digest(
        user_id=user.id,
        generated_at=datetime.now(timezone.utc),
        delivery_method="in_app",
        section_counts=section_counts,
        total_items=total,
    )
    session.add(digest)
    await session.flush()

    # Create digest items
    position = 0
    for section_name, section in sections.items():
        for item, prs, breakdown in section.items:
            clean_breakdown = {k: v for k, v in breakdown.items() if not k.startswith("_")}
            di = DigestItem(
                digest_id=digest.id,
                content_item_id=item.id,
                position=position,
                section=section_name,
                prs_score=prs,
                signal_breakdown=clean_breakdown,
            )
            session.add(di)
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


async def _synthesize_topic_clusters(
    items: list[ContentItem],
    session: AsyncSession,
) -> list[ContentItem]:
    """
    Detect groups of items covering the same story via embedding similarity.
    For each cluster of 2+ items, synthesize a combined summary via Groq and
    annotate the highest-PRS item with it; remove the duplicates from the list.
    """
    if len(items) < 2:
        return items

    # Only cluster items that have embeddings and summaries
    embeddable = [i for i in items if i.embedding is not None and i.summary_brief]
    non_embeddable = [i for i in items if i.embedding is None or not i.summary_brief]

    if len(embeddable) < 2:
        return items

    SYNTHESIS_THRESHOLD = 0.88
    vecs = np.array([i.embedding for i in embeddable], dtype=np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-8
    vecs = vecs / norms

    assigned: set[int] = set()
    clusters: list[list[int]] = []

    for i in range(len(embeddable)):
        if i in assigned:
            continue
        cluster = [i]
        for j in range(i + 1, len(embeddable)):
            if j in assigned:
                continue
            sim = float(np.dot(vecs[i], vecs[j]))
            if sim >= SYNTHESIS_THRESHOLD:
                cluster.append(j)
                assigned.add(j)
        assigned.add(i)
        clusters.append(cluster)

    # For clusters with multiple items, synthesize
    kept_indices: set[int] = set()
    try:
        from app.services.summarization.groq_client import GroqSummarizer, SummarizationResult
        groq = GroqSummarizer()
    except Exception:
        groq = None

    for cluster in clusters:
        if len(cluster) == 1:
            kept_indices.add(cluster[0])
            continue

        # Keep the first (highest-fetched) item, synthesize summary from all
        primary_idx = cluster[0]
        kept_indices.add(primary_idx)
        primary = embeddable[primary_idx]

        if groq is not None:
            try:
                from app.services.summarization.groq_client import SummarizationResult as SR
                pseudo_results = []
                for idx in cluster:
                    item = embeddable[idx]
                    pseudo_results.append(SR(
                        headline=item.summary_headline or item.title,
                        brief=item.summary_brief or "",
                        detailed=item.summary_detailed or "",
                        depth_score=item.content_depth_score or 0.5,
                        is_original_reporting=item.is_original_reporting or False,
                        has_citations=item.has_citations,
                        topic_clusters=item.topic_clusters or [],
                        reading_time_minutes=item.reading_time_minutes or 5,
                    ))
                topic_label = (primary.topic_clusters or [primary.title])[0]
                synthesized = await groq.synthesize_topic(pseudo_results, topic_label)
                if synthesized:
                    primary.summary_brief = synthesized
                    await session.flush()
            except Exception as e:
                logger.debug(f"Synthesis failed (non-fatal): {e}")

    # Build final list: kept items from embeddable + all non-embeddable
    result = [embeddable[i] for i in sorted(kept_indices)] + non_embeddable
    removed = len(embeddable) - len(kept_indices)
    if removed > 0:
        logger.info(f"Topic synthesis removed {removed} near-duplicate items")
    return result


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
    {"type": "depth_level", "text": "Was today's content the right depth — or would you prefer more in-depth analysis?"},
    {"type": "topic_accuracy", "text": "Did today's digest match your interests, or did anything feel off-topic?"},
    {"type": "source_quality", "text": "Were the sources today high quality and trustworthy for you?"},
    {"type": "depth_level", "text": "Were the articles too long, too short, or just right?"},
    {"type": "topic_accuracy", "text": "Was there a topic today you'd like to see more of?"},
    {"type": "source_quality", "text": "Did you discover any new sources today that you'd like to follow?"},
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

    num_prompts = 3 if user_age_days < 7 else 2
    # Pick a content item from the first section to anchor one of the prompts
    anchor_item_id = None
    for section in sections.values():
        if section.items:
            anchor_item_id = section.items[0][0].id  # (content, prs, breakdown)[0].id
            break

    for i in range(num_prompts):
        prompt_def = _EARLY_PROMPTS[(existing_count + i) % len(_EARLY_PROMPTS)]
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
    # Measure typical items-opened-per-digest over last 30 days
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    try:
        result = await session.execute(
            select(func.count(UserContentInteraction.id)).where(
                UserContentInteraction.user_id == user.id,
                UserContentInteraction.opened_at >= cutoff,
                UserContentInteraction.surfaced_in_digest == True,
            )
        )
        opens = result.scalar() or 0

        digests_result = await session.execute(
            select(func.count()).select_from(
                select(UserContentInteraction.content_item_id)
                .where(
                    UserContentInteraction.user_id == user.id,
                    UserContentInteraction.surfaced_in_digest == True,
                    UserContentInteraction.created_at >= cutoff,
                )
                .subquery()
            )
        )
        # Approximate number of digests from the period
        total_surfaced = digests_result.scalar() or 0
        if total_surfaced > 0:
            avg_opens = opens / max(1, total_surfaced / max(1, user.digest_max_items))
            # Target: digest length = 1.3x the average items the user opens
            target_length = max(5, min(30, round(avg_opens * 1.3)))
            # Only adjust if meaningfully different (>2 items off)
            if abs(target_length - user.digest_max_items) > 2:
                user.digest_max_items = target_length
                logger.info(f"Auto-adjusted digest length to {target_length} for user {user.id}")

        # Measure topical diversity over last 14 days for serendipity adjustment
        diversity_cutoff = datetime.now(timezone.utc) - timedelta(days=14)
        from sqlalchemy import text as sql_text
        div_result = await session.execute(
            sql_text("""
                SELECT COUNT(DISTINCT topic) as topic_count, COUNT(*) as total
                FROM (
                    SELECT jsonb_array_elements_text(ci.topic_clusters) as topic
                    FROM content_items ci
                    JOIN user_content_interactions uci ON ci.id = uci.content_item_id
                    WHERE uci.user_id = :uid
                      AND uci.created_at >= :cutoff
                      AND uci.read_completion_pct >= 0.5
                ) t
            """),
            {"uid": str(user.id), "cutoff": diversity_cutoff},
        )
        div_row = div_result.fetchone()
        if div_row and div_row[1] > 10:
            diversity_ratio = div_row[0] / max(1, div_row[1])
            # Narrow focus (low diversity) → boost serendipity; broad → reduce slightly
            if diversity_ratio < 0.3 and user.serendipity_percentage < 25:
                user.serendipity_percentage = min(25, user.serendipity_percentage + 3)
                logger.info(f"Increased serendipity to {user.serendipity_percentage}% for user {user.id}")
            elif diversity_ratio > 0.6 and user.serendipity_percentage > 10:
                user.serendipity_percentage = max(10, user.serendipity_percentage - 2)

        await session.flush()
    except Exception as e:
        logger.warning(f"digest preference adjustment failed (non-fatal): {e}")
