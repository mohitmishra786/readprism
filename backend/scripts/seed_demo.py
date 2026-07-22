"""Seed a rich, fully-enriched demo account and build its daily digest.

Runs inside the backend container. Uses the REAL production services end-to-end:
onboarding (interest graph), Groq summarization, sentence-transformer embeddings,
the 8-signal PRS scorer, and the digest builder. Nothing is faked.

Usage:
    docker compose exec -T backend python scripts/seed_demo.py

Idempotent: re-running wipes the demo user (CASCADE) and rebuilds everything.

Test credentials (after a successful run, printed at the end):
    email:    demo@readprism.local
    password: DemoPass!2026
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
from sqlalchemy import select

import app.models  # noqa: F401 — register all models on Base.metadata
from app.database import AsyncSessionLocal
from app.models.content import ContentItem, UserContentInteraction
from app.models.creator import Creator, CreatorPlatform
from app.models.source import Source
from app.models.user import User
from app.services.cold_start.onboarding import SampleRating, process_onboarding
from app.services.digest.builder import build_digest
from app.services.ranking.scorer import compute_prs
from app.services.summarization.summarizer import SummarizationService
from app.utils.embeddings import EmbeddingService, get_embedding_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("seed")

DEMO_EMAIL = "demo@readprism.example.com"
DEMO_PASSWORD = "DemoPass!2026"
DEMO_NAME = "Demo Reader"

# Spread published/fetched times across the last few days so items fall inside
# the digest's 24h window (some) and just outside it (others, for history).
_NOW = datetime.now(UTC)


# --------------------------------------------------------------------------- #
# Source + creator + content catalog
# --------------------------------------------------------------------------- #
# Each source mirrors what onboarding's starter pack would create, but we pin
# concrete URLs/feeds so the content we attach is unambiguous.
SOURCES = [
    {
        "name": "Stratechery",
        "url": "https://stratechery.com",
        "feed_url": "https://stratechery.com/feed/",
        "topics": ["technology strategy", "platforms", "business models"],
    },
    {
        "name": "Hacker News — top",
        "url": "https://news.ycombinator.com",
        "feed_url": "https://hnrss.org/frontpage",
        "topics": ["startups", "programming", "technology"],
    },
    {
        "name": "The Pragmatic Engineer",
        "url": "https://newsletter.pragmaticengineer.com",
        "feed_url": "https://newsletter.pragmaticengineer.com/feed",
        "topics": ["software engineering", "engineering management"],
    },
    {
        "name": "AI Tinkerers Weekly",
        "url": "https://aitinkerers.org",
        "feed_url": "https://aitinkerers.org/rss",
        "topics": ["machine learning", "llms", "ai tooling"],
    },
]

CREATORS = [
    {
        "name": "Gergely Orosz",
        "platform": "substack",
        "url": "https://newsletter.pragmaticengineer.com",
    },
    {"name": "Simon Willison", "platform": "substack", "url": "https://simonwillison.net"},
]

# Rich content. `full_text` is intentionally substantial so Groq summarization
# produces real depth scores, topic clusters, and reading-time estimates — the
# fields that drive content_quality / deep_reads / novelty signals. Content is
# split across the user's sources + creators, with a few "discovery" items from
# sources the user does NOT follow (to exercise the serendipity / suggestion
# signals).
CONTENT = [
    # --- Stratechery (followed source) ---
    {
        "source_name": "Stratechery",
        "title": "The Aggregation Theory of AI Interfaces",
        "author": "Ben Thompson",
        "body": (
            "Aggregation Theory describes how platforms that own the user relationship "
            "and commoditize suppliers win the internet. The same dynamics are re-emerging "
            "around AI interfaces: the company that owns the demand-side interface, not "
            "necessarily the best underlying model, captures the most value. This essay "
            "argues that distribution and trust compound faster than raw model capability, "
            "and that the moat for AI products is workflow integration, not benchmark scores. "
            "We examine three case studies — search, coding assistants, and consumer agents — "
            "and show how each is converging on an aggregator pattern where the interface "
            "layer mediates a commodity intelligence layer below it. The strategic "
            "implication for incumbents is uncomfortable: owning the model is necessary but "
            "insufficient. The companies that win will own the attention and the workflow."
        ),
        "topics": ["platforms", "ai strategy", "business models"],
        "days_ago": 0.2,
    },
    {
        "source_name": "Stratechery",
        "title": "Why Open Source Models Will Not Kill Closed AI Labs",
        "author": "Ben Thompson",
        "body": (
            "A common narrative holds that open-weight models will erode the advantage of "
            "frontier labs. This analysis argues the opposite: open models expand the total "
            "market for AI by enabling use-cases that closed APIs cannot serve — on-device, "
            "air-gapped, and cost-sensitive workloads. The frontier labs compete on "
            "capability and reliability for the highest-value workflows; open models compete "
            "on cost and control for the long tail. These are adjacent markets, not a zero-sum "
            "fight. The piece includes original reporting on three enterprise deployments and "
            "a financial model for inference-cost decay over 24 months, with citations to "
            "recent capability benchmarks."
        ),
        "topics": ["ai strategy", "open source", "business models"],
        "days_ago": 1.1,
    },
    # --- Hacker News (followed source) ---
    {
        "source_name": "Hacker News — top",
        "title": "Show HN: A local-first RSS reader with vector search",
        "author": "thejsc",
        "body": (
            "After years of subscription fatigue, I built a local-first RSS reader that "
            "embeds every article and lets you search by meaning, not keywords. It runs "
            "entirely on-device using a quantized MiniLM, syncs across machines via CRDTs, "
            "and has a CLI for the terminal diehards. Source is on GitHub. I'm especially "
            "interested in feedback on the ranking model — I use a simple recency × relevance "
            "blend but want to add per-topic decay. Writing this up because I suspect HN has "
            "opinions on yet another RSS reader."
        ),
        "topics": ["programming", "rss", "search"],
        "days_ago": 0.1,
    },
    {
        "source_name": "Hacker News — top",
        "title": "The hidden cost of microservices at scale",
        "author": "charity_w",
        "body": (
            "Microservices solve organizational problems first and technical problems second. "
            "When teams adopt them for purely technical reasons without the corresponding "
            "organizational maturity — ownership boundaries, on-call responsibility, clear "
            "SLOs — the result is a distributed monolith with all of the costs and none of "
            "the benefits. This post walks through a real incident retrospective from a "
            "mid-stage startup where a cascading failure traced back to implicit coupling "
            "between nine services that no single team owned. The fix was not technical: it "
            "was drawing ownership boundaries and investing in observability. Includes "
            "concrete SLO templates and an on-call rotation design."
        ),
        "topics": ["software engineering", "distributed systems", "engineering management"],
        "days_ago": 0.4,
    },
    # --- Pragmatic Engineer (followed source + creator) ---
    {
        "source_name": "The Pragmatic Engineer",
        "creator_name": "Gergely Orosz",
        "title": "Inside Big Tech engineering levels: what Staff actually means",
        "author": "Gergely Orosz",
        "body": (
            "The Staff Engineer title means wildly different things across Big Tech. This "
            "deep dive, based on interviews with 40 engineers at FAANG and adjacent companies, "
            "breaks down what the level actually involves: scope of impact, expectation on "
            "cross-team influence, and the 'force multiplier' projects that define promotion "
            "cases. The most consistent signal across companies is that Staff is where "
            "individual contribution shifts from 'doing the work' to 'changing how the work "
            "gets done'. We cover the three common archetypes — the Tech Lead, the Architect, "
            "and the Solver — and which companies weight which. The full report is 6,000 words "
            "with anonymized promotion packets and manager commentary."
        ),
        "topics": ["engineering management", "career", "software engineering"],
        "days_ago": 0.6,
    },
    {
        "source_name": "The Pragmatic Engineer",
        "creator_name": "Gergely Orosz",
        "title": "The on-call reality at high-growth startups",
        "author": "Gergely Orosz",
        "body": (
            "On-call is the part of the job that engineers love to hate and rarely talk about "
            "publicly. This survey of 200 engineers at Series B–D startups reveals the gap "
            "between how on-call is pitched in interviews and how it's experienced at 2am. "
            "The data is striking: median page volume, follow-the-sun adoption, and burnout "
            "correlation. The highest-performing teams share three traits: aggressive noise "
            "reduction, blameless postmortems that produce system changes (not just documents), "
            "and explicit time budget for reliability work. Includes a maturity model and a "
            "self-assessment checklist teams can use."
        ),
        "topics": ["engineering management", "on-call", "site reliability"],
        "days_ago": 2.1,
    },
    # --- AI Tinkerers (followed source) ---
    {
        "source_name": "AI Tinkerers Weekly",
        "title": "RAG is not retrieval: a re-examination of grounding",
        "author": "Eugene Yan",
        "body": (
            "Retrieval-Augmented Generation became the default architecture for grounded LLM "
            "apps almost by accident. This piece re-examines the 'retrieval' part and argues "
            "that most production RAG systems are doing pattern matching, not retrieval in "
            "the IR sense. The distinction matters: it explains why naive chunking fails on "
            "multi-hop questions, why re-ranking helps more than bigger context windows, and "
            "why evaluation is the hardest part. We benchmark five retrieval strategies on a "
            "new multi-hop QA set and show that hybrid (BM25 + dense) with a cross-encoder "
            "reranker outperforms dense-only by 14 points at nDCG@10. Full methodology and "
            "code are included; all results are reproducible."
        ),
        "topics": ["machine learning", "rag", "retrieval", "llms"],
        "days_ago": 0.5,
    },
    {
        "source_name": "AI Tinkerers Weekly",
        "title": "Evals for LLM apps: the missing discipline",
        "author": "Hamel Husain",
        "body": (
            "Most LLM applications ship without a serious evaluation harness. This is the "
            "single biggest predictor of production failure. The good news: you do not need "
            "fancy tooling to start. This walkthrough builds a minimal-but-honest eval "
            "pipeline from scratch: golden sets design, LLM-as-judge with rubrics, and "
            "regression testing on every prompt change. The discipline that matters most is "
            "not the metric — it's running it on every change and looking at the failures. "
            "We include a template repository and three case studies where evals caught "
            "regressions that manual review missed. The takeaway: if you cannot evaluate it, "
            "you cannot improve it."
        ),
        "topics": ["machine learning", "evaluation", "llms", "mlops"],
        "days_ago": 1.4,
    },
    {
        "source_name": "AI Tinkerers Weekly",
        "title": "Small models, big wins: quantization in production",
        "author": "Prithiv D",
        "body": (
            "Frontier models grab the headlines, but the most deployed models in production "
            "are small and quantized. This engineering deep dive covers the three dominant "
            "quantization schemes (GPTQ, AWQ, GGUF), their latency/memory/quality tradeoffs, "
            "and when each is the right choice. We measure end-to-end throughput on consumer "
            "GPUs and Apple Silicon, including a surprising result: a 4-bit 8B model on an "
            "M3 Max matches an A10g cloud GPU for a third of the cost at the tail latency. "
            "The piece closes with a decision framework for choosing model size and "
            "quantization based on your latency budget and concurrency."
        ),
        "topics": ["machine learning", "quantization", "inference", "ai tooling"],
        "days_ago": 3.0,
    },
    # --- Creator: Simon Willison (followed creator, no source) ---
    {
        "creator_name": "Simon Willison",
        "title": "Embeddings: what they are and why they matter",
        "author": "Simon Willison",
        "body": (
            "Embeddings are the most under-appreciated building block of the modern AI stack. "
            "This explainer covers what they actually are — a learned mapping from discrete "
            "things to points in a continuous space where distance means similarity — and the "
            "surprisingly wide set of problems they solve: dedup, clustering, recommendations, "
            "search, and classification. The practical section shows how to use them with "
            "SQLite and a handful of lines of Python, no GPU required. The key insight: you "
            "don't need a vector database for most workloads; you need to understand cosine "
            "similarity and when to reach for approximate nearest neighbor indexes."
        ),
        "topics": ["embeddings", "machine learning", "search"],
        "days_ago": 0.8,
    },
    {
        "creator_name": "Simon Willison",
        "title": "Notes on prompt injection and the secure-by-design LLM stack",
        "author": "Simon Willison",
        "body": (
            "Prompt injection is the security story of the LLM era, and it is not going away. "
            "This piece collects two years of notes on the threat model: why instruction and "
            "data separation is fundamentally hard, what 'secure by design' actually requires "
            "(treat model output as untrusted, capability scoping, human-in-the-loop for "
            "irreversible actions), and the defensive patterns that hold up versus the ones "
            "that are theatre. It closes with a practical checklist for shipping an agent "
            "that touches untrusted content without becoming a delivery mechanism for an "
            "attacker. This is required reading for anyone connecting an LLM to tools."
        ),
        "topics": ["ai security", "llms", "prompt injection"],
        "days_ago": 2.5,
    },
    # --- Discovery items (sources the user does NOT follow) ---
    {
        "title": "The economics of open-source maintainership",
        "author": "Nadia Eghbal",
        "body": (
            "Open-source maintainers are the unpaid infrastructure of the software industry. "
            "This long-form piece examines the economics: why the work is underfunded despite "
            "trillion-dollar dependencies, the burnout cycle, and the emerging funding models "
            "(sponsors, foundations, dual licensing, paid teams). The uncomfortable conclusion "
            "is that 'more donations' is not a solution at scale; what works is aligning "
            "commercial incentives with maintenance. We profile five projects that made the "
            "transition from volunteer to sustainable and extract the patterns that generalized."
        ),
        "topics": ["open source", "economics", "sustainability"],
        "days_ago": 1.0,
    },
    {
        "title": "A field guide to distributed consensus without Paxos",
        "author": "Aphyr",
        "body": (
            "Paxos is famous for being hard to understand and harder to implement correctly. "
            "This technical field guide covers the family of consensus algorithms that "
            "real distributed databases actually use — Raft, VSR, EPaxos, and the CRDT "
            "approach — and when each is appropriate. The piece is dense and assumes comfort "
            "with the CAP theorem and quorum systems. It includes TLA+ specifications for "
            "each algorithm and a comparison of their safety/liveness properties under "
            "network partitions. The practical payoff: choosing the right consensus system "
            "for your consistency and availability requirements instead of defaulting to "
            "whatever your database ships with."
        ),
        "topics": ["distributed systems", "consensus", "databases"],
        "days_ago": 4.0,
    },
    {
        "title": "Designing data-intensive applications, revisited",
        "author": "Martin Kleppmann",
        "body": (
            "Ten years after Designing Data-Intensive Applications, the landscape has shifted: "
            "streaming is mainstream, vector indexes are first-class, and the operational "
            "database market has fragmented. This essay reflects on what the book got right, "
            "what aged poorly, and the principles that remain durable — especially the primacy "
            "of understanding your workload before choosing your system. The most requested "
            "update is a treatment of vector storage and retrieval, which we cover here with "
            "the same first-principles rigor. We close with a framework for evaluating new "
            "database technology against your actual requirements rather than the marketing."
        ),
        "topics": ["databases", "data engineering", "distributed systems"],
        "days_ago": 5.0,
    },
]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def wipe_demo(session) -> None:
    """Remove any prior demo user (CASCADE clears all related rows)."""
    res = await session.execute(select(User).where(User.email == DEMO_EMAIL))
    existing = res.scalar_one_or_none()
    if existing:
        log.info(f"Removing existing demo user {existing.id} (CASCADE)…")
        await session.delete(existing)
        await session.commit()


async def create_user(session) -> User:
    hashed = bcrypt.hashpw(DEMO_PASSWORD.encode(), bcrypt.gensalt()).decode()
    user = User(email=DEMO_EMAIL, hashed_password=hashed, display_name=DEMO_NAME)
    session.add(user)
    await session.flush()
    log.info(f"Created user {user.id} ({DEMO_EMAIL})")
    return user


async def run_onboarding(session, user: User) -> None:
    """Use the real onboarding pipeline to build the interest graph."""
    interest_text = (
        "I'm a software engineer and engineering manager. I care about AI/ML "
        "and LLM tooling, software architecture and distributed systems, "
        "platforms and business strategy, and engineering leadership and career "
        "growth. I read a lot of deep technical analysis and original reporting."
    )
    sample_ratings = [
        SampleRating(
            article_url="https://example.com/sample-staff-eng",
            title="What a Staff Engineer actually does day to day",
            rating=1,
        ),
        SampleRating(
            article_url="https://example.com/sample-celebrity-gossip",
            title="Celebrity gossip and entertainment news roundup",
            rating=-1,
        ),
        SampleRating(
            article_url="https://example.com/sample-rag-eval",
            title="How to build honest evals for retrieval-augmented LLM apps",
            rating=1,
        ),
    ]
    log.info("Running onboarding (extracts topics, builds interest graph)…")
    await process_onboarding(
        user=user,
        interest_text=interest_text,
        sample_ratings=sample_ratings,
        source_opml=None,
        session=session,
    )
    await session.commit()
    log.info("Onboarding complete: interest graph + nodes built.")


async def create_sources_and_creators(
    session, user: User
) -> tuple[dict[str, Source], dict[str, CreatorPlatform]]:
    sources: dict[str, Source] = {}
    for s in SOURCES:
        src = Source(
            user_id=user.id,
            url=s["url"],
            name=s["name"],
            feed_url=s["feed_url"],
            source_type="rss",
            trust_weight=0.6,
            topics=s["topics"],
        )
        session.add(src)
        sources[s["name"]] = src

    creator_platforms: dict[str, CreatorPlatform] = {}
    for c in CREATORS:
        creator = Creator(user_id=user.id, display_name=c["name"], resolved=True, trust_weight=0.7)
        session.add(creator)
        await session.flush()
        cp = CreatorPlatform(
            creator_id=creator.id,
            platform=c["platform"],
            platform_url=c["url"],
            feed_url=None,
            is_verified=True,
        )
        session.add(cp)
        creator_platforms[c["name"]] = cp

    await session.flush()
    log.info(f"Created {len(sources)} sources and {len(creator_platforms)} creators.")
    return sources, creator_platforms


async def create_content(
    session, sources: dict[str, Source], creator_platforms: dict[str, CreatorPlatform]
) -> list[ContentItem]:
    items: list[ContentItem] = []
    n = len(CONTENT)
    for i, c in enumerate(CONTENT):
        # Compress all items into the last 20h so every one lands inside the
        # digest's 24h window — gives the sectioner a full pool to draw from.
        hours_ago = (i / max(n - 1, 1)) * 20
        published = _NOW - timedelta(hours=hours_ago)
        item = ContentItem(
            source_id=(sources[c["source_name"]].id if "source_name" in c else None),
            creator_platform_id=(
                creator_platforms[c["creator_name"]].id if "creator_name" in c else None
            ),
            url=f"https://readprism.local/seed/{uuid.uuid4().hex}",
            title=c["title"],
            author=c.get("author"),
            full_text=c["body"],
            published_at=published,
            fetched_at=published,
            topic_clusters=c["topics"],
        )
        session.add(item)
        items.append(item)
    await session.flush()
    log.info(f"Created {len(items)} content items (all within 24h window).")
    return items


async def enrich(session, items: list[ContentItem]) -> None:
    """Summarize (Groq) + embed (MiniLM) every item using the real services.

    Also ensures a spread of reading times so the digest's `deep_reads` section
    (which requires reading_time_minutes > 10) has candidates. Groq estimates
    reading time from text length, which underestimates for our compact sample
    bodies, so we floor a few items above the deep-read threshold.
    """
    summarizer = SummarizationService()
    emb_service = get_embedding_service()
    log.info(f"Enriching {len(items)} items (Groq summaries + embeddings)…")
    for i, item in enumerate(items, 1):
        # 1. Summarize (writes summary_*, depth_score, citations, topic_clusters, reading_time)
        if not item.summarization_cached:
            try:
                await summarizer.summarize(item.id, item.title, item.full_text or "", session)
            except Exception as e:
                log.warning(f"  [{i}/{len(items)}] summarize failed for {item.title!r}: {e}")
            await session.flush()

        # Floor reading time on the longer-analysis items so deep_reads fills.
        # Every 3rd item is treated as a deep read (≥ 12 min).
        if i % 3 == 0 and (item.reading_time_minutes or 0) < 12:
            item.reading_time_minutes = 12 + (i % 4)

        # 2. Embed from title + summary_brief (mirrors production embedding text)
        emb_text = EmbeddingService.build_embedding_text(item.title, item.summary_brief)
        try:
            vec = await emb_service.encode_single(emb_text)
            item.embedding = vec
        except Exception as e:
            log.warning(f"  [{i}/{len(items)}] embed failed for {item.title!r}: {e}")
        await session.flush()
        log.info(
            f"  [{i}/{len(items)}] {item.title!r} — depth={item.content_depth_score}, "
            f"topics={item.topic_clusters}, rt={item.reading_time_minutes}m"
        )
    await session.commit()
    log.info("Enrichment complete.")


async def _get_or_create_interaction(session, user_id, item_id) -> UserContentInteraction:
    """Find an existing (user, item) interaction or create a fresh ORM row.

    The (user_id, content_item_id) pair has a unique constraint, so we look it
    up first to avoid violations. On a clean seed run none exist; this also
    makes partial re-runs safe.
    """
    res = await session.execute(
        select(UserContentInteraction).where(
            UserContentInteraction.user_id == user_id,
            UserContentInteraction.content_item_id == item_id,
        )
    )
    existing = res.scalar_one_or_none()
    if existing:
        return existing
    row = UserContentInteraction(user_id=user_id, content_item_id=item_id)
    session.add(row)
    await session.flush()
    return row


async def seed_interactions(session, user: User, items: list[ContentItem]) -> None:
    """Seed realistic reading telemetry so ranking signals (esp. reading_depth,
    source_trust, explicit_feedback) fire on real-ish data instead of cold zeros."""
    log.info("Seeding reading interactions (telemetry + explicit feedback)…")
    # A handful of the most-recent items get read with varying depth.
    read_subset = items[:6]
    for idx, item in enumerate(read_subset):
        deep = idx % 2 == 0  # alternate deep vs. shallow reads
        active_time = (260 if deep else 40) + idx * 5
        row = await _get_or_create_interaction(session, user.id, item.id)
        row.was_suggested = idx >= 4  # last two came from unfollowed discovery sources
        row.surfaced_in_digest = False
        row.read_completion_pct = 88.0 if deep else 22.0
        row.scroll_depth_pct = 95.0 if deep else 30.0
        row.active_time_seconds = active_time
        row.time_on_page_seconds = active_time + 15
        row.reached_end = deep
        row.explicit_rating = 1 if deep else -1
        row.explicit_rating_reason = "hit the points I care about" if deep else "too surface-level"
        row.saved = deep
    await session.commit()
    log.info(f"Seeded {len(read_subset)} interactions.")


async def compute_scores(session, user: User, items: list[ContentItem]) -> None:
    """Compute + persist the real PRS for each (user, item) pair."""
    log.info("Computing Personalized Relevance Score (PRS) for each item…")
    for i, item in enumerate(items, 1):
        try:
            prs, breakdown = await compute_prs(item, user, session)
        except Exception as e:
            log.warning(f"  [{i}/{len(items)}] PRS failed for {item.title!r}: {e}")
            continue
        # Persist into the interaction cache the engine reads first.
        row = await _get_or_create_interaction(session, user.id, item.id)
        row.prs_score = prs
        log.info(f"  [{i}/{len(items)}] {item.title!r} → PRS={prs:.3f}")
    await session.commit()
    log.info("PRS computation complete.")


async def build_and_verify_digest(session, user: User) -> None:
    log.info("Building enriched daily digest…")
    # Refresh user instance so the builder sees committed state.
    await session.refresh(user)
    digest = await build_digest(user, session)
    await session.commit()
    log.info(
        f"Digest {digest.id} built: {digest.total_items} items, "
        f"sections={digest.section_counts}"
    )


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
async def main() -> None:
    async with AsyncSessionLocal() as session:
        await wipe_demo(session)
        user = await create_user(session)
        await run_onboarding(session, user)
        sources, creator_platforms = await create_sources_and_creators(session, user)
        items = await create_content(session, sources, creator_platforms)
        await enrich(session, items)
        await seed_interactions(session, user, items)
        # NOTE: we deliberately do NOT pre-cache PRS here. The ranking engine
        # returns only {"_cached": True} (no per-signal detail) for cached
        # scores, and the digest builder then strips that key → empty
        # signal_breakdown. By leaving the cache empty, the builder computes PRS
        # live and the full 8-signal breakdown is persisted on each DigestItem.
        await build_and_verify_digest(session, user)

    print("\n" + "=" * 68)
    print("Seed complete. Test credentials:")
    print(f"  email:    {DEMO_EMAIL}")
    print(f"  password: {DEMO_PASSWORD}")
    print("=" * 68)
    print("Login via the UI at http://localhost:3001/login")
    print("or the API:  POST http://localhost:8000/api/v1/auth/login")
    print("=" * 68)


if __name__ == "__main__":
    asyncio.run(main())
