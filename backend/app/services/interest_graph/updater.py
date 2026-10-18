from __future__ import annotations

import itertools

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem, UserContentInteraction
from app.services.interest_graph.graph import InterestGraphManager
from app.utils.embeddings import get_embedding_service
from app.utils.logging import get_logger

logger = get_logger(__name__)

graph_manager = InterestGraphManager()

# Scalability: limit edge reinforcement to top-N topics per content item.
# With 20 topics, combinations(20,2) = 190 writes; capped at top-5 → max 10 writes.
MAX_TOPICS_FOR_EDGE_UPDATE = 5

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
    if completion >= 0.50:  # (already < 0.85 here)
        return 0.4
    return 0.0


def _normalise(signal: float) -> float:
    return max(-1.0, min(1.0, signal))


async def update_from_interaction(
    interaction: UserContentInteraction,
    content: ContentItem,
    session: AsyncSession,
) -> bool:
    """Apply this interaction's signal to the interest graph and trust weights.

    Idempotent per interaction (#105): the reader flushes telemetry every 20 s
    and every flush re-enqueues this update. Only the change between the
    signal already applied (`graph_signal_applied`) and the current one is
    applied, edges are reinforced once per read, and reinforcement counts move
    only on the first application. Returns True if anything changed.
    """
    signal_strength = _compute_signal_strength(interaction)
    previous = interaction.graph_signal_applied
    first_application = previous is None
    delta = signal_strength - (previous or 0.0)
    if not first_application and abs(delta) < 1e-9:
        return False

    topic_clusters = content.topic_clusters or []
    if topic_clusters:
        embedding_service = get_embedding_service()
        topic_embeddings = await embedding_service.encode_batch_cached(topic_clusters)

        nodes = []
        for label, emb in zip(topic_clusters, topic_embeddings, strict=False):
            node = await graph_manager.get_or_create_node(
                user_id=interaction.user_id,
                topic_label=label,
                topic_embedding=emb,
                session=session,
            )
            if delta:
                await graph_manager.reinforce_node(node, delta, session, count=first_application)
            nodes.append(node)

        # Co-reading edges once per read: when the applied signal first turns
        # positive. Cap to the top-N nodes by weight to bound DB writes
        # (combinations(5, 2) = 10).
        became_positive = signal_strength > 0 and (previous is None or previous <= 0)
        if became_positive:
            top_nodes = sorted(nodes, key=lambda n: n.weight, reverse=True)[
                :MAX_TOPICS_FOR_EDGE_UPDATE
            ]
            for node_a, node_b in itertools.combinations(top_nodes, 2):
                await graph_manager.reinforce_edge(
                    user_id=interaction.user_id,
                    node_a_id=node_a.id,
                    node_b_id=node_b.id,
                    session=session,
                )
    else:
        logger.debug(f"No topic clusters for content {content.id}, skipping graph nodes")

    trust_delta = _normalise(signal_strength) - _normalise(previous or 0.0)
    await _update_source_trust(interaction, content, trust_delta, first_application, session)

    interaction.graph_signal_applied = signal_strength
    await session.flush()
    logger.debug(
        f"Updated interest graph for user {interaction.user_id}: "
        f"{len(topic_clusters)} topics, signal={signal_strength:.2f} (delta {delta:+.2f})"
    )
    return True


async def _update_source_trust(
    interaction: UserContentInteraction,
    content: ContentItem,
    normalised_delta: float,
    first_application: bool,
    session: AsyncSession,
) -> None:
    """Nudge the reader's source trust by the change in this interaction's signal."""
    if not normalised_delta:
        return
    from app.services.feed_identity import user_source_for_item

    # The reader's own source for this feed: the item may be stored under
    # another subscriber's source row, and writing there changed someone
    # else's trust (#108). Only the change since the last application is
    # applied (#105).
    source = await user_source_for_item(session, interaction.user_id, content.source_id)
    if source is not None:
        delta = TRUST_LEARN_RATE * normalised_delta
        source.trust_weight = float(max(TRUST_MIN, min(TRUST_MAX, source.trust_weight + delta)))
        await session.flush()

    # Update per-creator-per-topic trust if content has a creator
    if content.creator_platform_id is not None:
        await _update_creator_topic_trust(
            interaction, content, normalised_delta, session, count=first_application
        )


async def _update_creator_topic_trust(
    interaction: UserContentInteraction,
    content: ContentItem,
    normalised_signal: float,
    session: AsyncSession,
    *,
    count: bool = True,
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
        if count:
            trust_record.interaction_count += 1

    if topic_clusters:
        await session.flush()
