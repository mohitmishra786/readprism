from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import UserContentInteraction
from app.models.interest_graph import InterestNode
from app.models.source import Source
from app.models.user import User
from app.services.interest_graph.graph import InterestGraphManager
from app.services.summarization.groq_client import GroqSummarizer
from app.utils.embeddings import get_embedding_service
from app.utils.logging import get_logger

logger = get_logger(__name__)
graph_manager = InterestGraphManager()


@dataclass
class SampleRating:
    article_url: str
    title: str
    rating: int  # 1=would read, 0=maybe, -1=not for me


async def process_onboarding(
    user: User,
    interest_text: str,
    sample_ratings: list[SampleRating],
    source_opml: Optional[str],
    session: AsyncSession,
) -> None:
    embedding_service = get_embedding_service()

    # 1. Extract topics from interest text using Groq
    groq = GroqSummarizer()
    topics = await groq.extract_topics(interest_text)
    if not topics:
        topics = _fallback_topic_extract(interest_text)

    # 2. Embed topics and create initial nodes
    topic_embeddings = await embedding_service.encode_batch_cached(topics)
    for label, emb in zip(topics, topic_embeddings):
        node = await graph_manager.get_or_create_node(
            user_id=user.id,
            topic_label=label,
            topic_embedding=emb,
            session=session,
        )
        # Start above neutral — confirmed interest from onboarding
        node.weight = 0.6
        await session.flush()

    # 3. Process sample ratings as interaction signals
    for sr in sample_ratings:
        if sr.rating == 0:
            continue
        signal = 0.8 if sr.rating == 1 else -0.4
        # Encode the title as a topic proxy
        emb = await embedding_service.encode_single(sr.title)
        node = await graph_manager.get_or_create_node(
            user_id=user.id,
            topic_label=f"sample:{sr.title[:40]}",
            topic_embedding=emb,
            session=session,
        )
        await graph_manager.reinforce_node(node, signal, session)

    # 4. Parse OPML and create sources
    if source_opml:
        await _import_opml(user.id, source_opml, session)

    # 5. Mark onboarding complete
    user.onboarding_complete = True
    user.interest_text = interest_text
    await session.flush()
    logger.info(f"Onboarding complete for user {user.id}: {len(topics)} topics extracted")


def _fallback_topic_extract(text: str) -> list[str]:
    import re
    words = re.findall(r"\b[A-Za-z][a-z]+(\s[A-Z][a-z]+)*\b", text)
    return list(set(w.strip() for w in words if len(w) > 4))[:8]


async def _import_opml(user_id: uuid.UUID, opml_content: str, session: AsyncSession) -> None:
    try:
        import listparser
        result = listparser.parse(opml_content)
        for feed in result.feeds:
            url = feed.url or feed.feed or ""
            if not url:
                continue
            source = Source(
                user_id=user_id,
                url=url,
                name=feed.title or url,
                feed_url=url,
                source_type="rss",
            )
            session.add(source)
        await session.flush()
        logger.info(f"Imported {len(result.feeds)} OPML sources for user {user_id}")
    except ImportError:
        logger.warning("listparser not installed, OPML import skipped")
    except Exception as e:
        logger.error(f"OPML import failed: {e}")
