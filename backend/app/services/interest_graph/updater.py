from __future__ import annotations

import itertools
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem, UserContentInteraction
from app.models.source import Source
from app.services.interest_graph.graph import InterestGraphManager
from app.utils.embeddings import get_embedding_service
from app.utils.logging import get_logger

logger = get_logger(__name__)

graph_manager = InterestGraphManager()

# Trust weight learning constants
TRUST_LEARN_RATE = 0.02
TRUST_MIN = 0.1
TRUST_MAX = 1.0


def _compute_signal_strength(interaction: UserContentInteraction) -> float:
    if interaction.explicit_rating == 1:
        return 1.0
    if interaction.explicit_rating == -1:
        return -0.8

    completion = interaction.read_completion_pct or 0.0
    time_on_page = interaction.time_on_page_seconds or 0

    if interaction.saved and (interaction.saved_read_at is not None):
        return 0.9
    if interaction.saved:
        return 0.1
    if time_on_page < 10 and completion < 0.1:
        return -0.2
    if completion >= 0.85:
        signal = 0.8
        if interaction.was_suggested:
            signal = 1.2  # capped in reinforce_node
        return signal
    if 0.50 <= completion < 0.85:
        return 0.4
    return 0.0


async def update_from_interaction(
    interaction: UserContentInteraction,
    content: ContentItem,
    session: AsyncSession,
) -> None:
    topic_clusters = content.topic_clusters or []
    if not topic_clusters:
        logger.debug(f"No topic clusters for content {content.id}, skipping graph update")
        return

    signal_strength = _compute_signal_strength(interaction)
    embedding_service = get_embedding_service()

    # Embed topic labels if needed
    topic_embeddings = await embedding_service.encode_batch_cached(topic_clusters)

    # Get or create nodes
    nodes = []
    for label, emb in zip(topic_clusters, topic_embeddings):
        node = await graph_manager.get_or_create_node(
            user_id=interaction.user_id,
            topic_label=label,
            topic_embedding=emb,
            session=session,
        )
        await graph_manager.reinforce_node(node, signal_strength, session)
        nodes.append(node)

    # Reinforce edges between all pairs of topics in this content
    for node_a, node_b in itertools.combinations(nodes, 2):
        await graph_manager.reinforce_edge(
            user_id=interaction.user_id,
            node_a_id=node_a.id,
            node_b_id=node_b.id,
            session=session,
        )

    # Update source trust weight based on behavioral signal
    await _update_source_trust(interaction, content, signal_strength, session)

    logger.debug(
        f"Updated interest graph for user {interaction.user_id}: "
        f"{len(nodes)} nodes, signal={signal_strength:.2f}"
    )


async def _update_source_trust(
    interaction: UserContentInteraction,
    content: ContentItem,
    signal_strength: float,
    session: AsyncSession,
) -> None:
    """Nudge source trust_weight up or down based on behavioral signal."""
    if content.source_id is None:
        return
    result = await session.execute(select(Source).where(Source.id == content.source_id))
    source = result.scalar_one_or_none()
    if source is None:
        return

    # Normalise signal to [-1, 1] range
    normalised = max(-1.0, min(1.0, signal_strength))
    delta = TRUST_LEARN_RATE * normalised
    source.trust_weight = float(max(TRUST_MIN, min(TRUST_MAX, source.trust_weight + delta)))
    await session.flush()

    # Update per-creator-per-topic trust if content has a creator
    if content.creator_platform_id is not None:
        await _update_creator_topic_trust(interaction, content, normalised, session)


async def _update_creator_topic_trust(
    interaction: UserContentInteraction,
    content: ContentItem,
    normalised_signal: float,
    session: AsyncSession,
) -> None:
    """
    Update trust at the creator × topic level.
    Each topic cluster in the content gets its own trust record per user × creator.
    """
    from app.models.creator import CreatorPlatform
    from app.models.creator_trust import CreatorTopicTrust

    # Resolve creator_id from creator_platform_id
    platform_result = await session.execute(
        select(CreatorPlatform).where(CreatorPlatform.id == content.creator_platform_id)
    )
    platform = platform_result.scalar_one_or_none()
    if platform is None:
        return

    topic_clusters = content.topic_clusters or []
    for topic_label in topic_clusters:
        trust_result = await session.execute(
            select(CreatorTopicTrust).where(
                CreatorTopicTrust.user_id == interaction.user_id,
                CreatorTopicTrust.creator_id == platform.creator_id,
                CreatorTopicTrust.topic_label == topic_label,
            )
        )
        trust_record = trust_result.scalar_one_or_none()

        if trust_record is None:
            trust_record = CreatorTopicTrust(
                user_id=interaction.user_id,
                creator_id=platform.creator_id,
                topic_label=topic_label,
                trust_weight=0.5,
                interaction_count=0,
            )
            session.add(trust_record)

        delta = TRUST_LEARN_RATE * normalised_signal
        trust_record.trust_weight = float(
            max(TRUST_MIN, min(TRUST_MAX, trust_record.trust_weight + delta))
        )
        trust_record.interaction_count += 1

    if topic_clusters:
        await session.flush()
