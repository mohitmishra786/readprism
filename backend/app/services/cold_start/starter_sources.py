"""Starter source pack — curated high-quality RSS feeds keyed by interest cluster.

Cold-start mitigation: when a new user's onboarding topics match a cluster, we
seed these sources so their first digest isn't empty. The collaborative-warmup
layer needs *other users'* data to work; until the product has that network
effect, a curated pack is what makes day-1 feel smart.

Each cluster maps to a list of (name, url, feed_url). Feeds here are
well-maintained, full-text-friendly, and broad enough to seed a real feed.
Topics are matched case-insensitively as substrings against the user's
extracted interest topics.
"""

from __future__ import annotations

# Each entry: cluster keyword(s) → list of seed sources.
# Keep feeds to reputable, RSS-friendly publications to minimize scraping burden.
STARTER_SOURCES: dict[str, list[dict]] = {
    "technology": [
        {
            "name": "Hacker News (front page)",
            "url": "https://news.ycombinator.com/",
            "feed_url": "https://news.ycombinator.com/rss",
        },
        {
            "name": "Ars Technica",
            "url": "https://arstechnica.com/",
            "feed_url": "https://feeds.arstechnica.com/arstechnica/index",
        },
        {
            "name": "The Verge",
            "url": "https://www.theverge.com/",
            "feed_url": "https://www.theverge.com/rss/index.xml",
        },
    ],
    "ai": [
        {
            "name": "Simon Willison",
            "url": "https://simonwillison.net/",
            "feed_url": "https://simonwillison.net/atom/everything/",
        },
        {
            "name": "Import AI",
            "url": "https://importai.substack.com/",
            "feed_url": "https://importai.substack.com/feed",
        },
        {
            "name": "Hugging Face Blog",
            "url": "https://huggingface.co/blog",
            "feed_url": "https://huggingface.co/blog/feed.xml",
        },
    ],
    "machine_learning": [
        {
            "name": "Google Research Blog",
            "url": "https://research.google/blog/",
            "feed_url": "https://research.google/blog/rss/",
        },
        {
            "name": "Machine Learning Mastery",
            "url": "https://machinelearningmastery.com/",
            "feed_url": "https://machinelearningmastery.com/feed/",
        },
    ],
    "programming": [
        {
            "name": "Hacker News (front page)",
            "url": "https://news.ycombinator.com/",
            "feed_url": "https://news.ycombinator.com/rss",
        },
    ],
    "startups": [
        {
            "name": "Paul Graham essays",
            "url": "http://www.paulgraham.com/",
            "feed_url": "https://www.aaronstacy.com/rss/paulgraham.xml",
        },
        {
            "name": "Stratechery",
            "url": "https://stratechery.com/",
            "feed_url": "https://stratechery.com/feed/",
        },
    ],
    "business": [
        {
            "name": "Harvard Business Review",
            "url": "https://hbr.org/",
            "feed_url": "https://hbr.org/the-latest/rss",
        },
        {
            "name": "Stratechery",
            "url": "https://stratechery.com/",
            "feed_url": "https://stratechery.com/feed/",
        },
    ],
    "finance": [
        {
            "name": "Bloomberg Markets",
            "url": "https://www.bloomberg.com/markets",
            "feed_url": "https://feeds.bloomberg.com/markets/news.rss",
        },
    ],
    "science": [
        {
            "name": "Nature",
            "url": "https://www.nature.com/",
            "feed_url": "https://www.nature.com/nature.rss",
        },
        {
            "name": "Quanta Magazine",
            "url": "https://www.quantamagazine.org/",
            "feed_url": "https://www.quantamagazine.org/feed/",
        },
    ],
    "design": [
        {
            "name": "Smashing Magazine",
            "url": "https://www.smashingmagazine.com/",
            "feed_url": "https://www.smashingmagazine.com/feed/",
        },
        {
            "name": "A List Apart",
            "url": "https://alistapart.com/",
            "feed_url": "https://alistapart.com/main/feed/",
        },
    ],
    "product": [
        {
            "name": "Lenny's Newsletter",
            "url": "https://www.lennysnewsletter.com/",
            "feed_url": "https://www.lennysnewsletter.com/feed",
        },
        {
            "name": "Mind the Product",
            "url": "https://www.mindtheproduct.com/",
            "feed_url": "https://www.mindtheproduct.com/feed/",
        },
    ],
    "distributed_systems": [
        {
            "name": "Martin Kleppmann",
            "url": "https://martin.kleppmann.com/",
            "feed_url": "https://martin.kleppmann.com/feed/",
        },
    ],
    "data_engineering": [
        {"name": "Julia Evans", "url": "https://jvns.ca/", "feed_url": "https://jvns.ca/atom.xml"},
    ],
    "security": [
        {
            "name": "Krebs on Security",
            "url": "https://krebsonsecurity.com/",
            "feed_url": "https://krebsonsecurity.com/feed/",
        },
        {
            "name": "Schneier on Security",
            "url": "https://www.schneier.com/",
            "feed_url": "https://www.schneier.com/feed/atom/",
        },
    ],
}

# Synonyms / aliases so topic text maps to clusters even when worded differently.
CLUSTER_ALIASES: dict[str, list[str]] = {
    "ai": [
        "artificial intelligence",
        "llm",
        "llms",
        "large language model",
        "large language models",
        "generative ai",
        "deep learning",
    ],
    "machine_learning": ["ml", "neural network", "data science"],
    "programming": ["software engineering", "coding", "developer", "software development"],
    "startups": ["entrepreneurship", "venture capital", "startup"],
    "business": ["strategy", "management", "operations"],
    "finance": ["investing", "markets", "economics", "stocks"],
    "science": ["research", "physics", "biology", "climate"],
    "design": ["ux", "ui", "user experience", "typography"],
    "product": ["product management", "product strategy", "pm"],
    "distributed_systems": ["distributed systems", "consensus", "databases", "systems"],
    "data_engineering": ["data engineering", "data", "analytics", "pipelines"],
    "security": ["infosec", "cybersecurity", "cryptography", "privacy"],
    "technology": ["tech", "gadgets", "hardware", "software"],
}


def match_clusters(topics: list[str]) -> set[str]:
    """Return the set of cluster keys whose keywords/aliases appear in the topics.

    Matching is token-based (word-boundary) rather than raw substring, so short
    aliases like "ml", "ui", "pm" don't false-match inside unrelated words.
    Multi-word aliases (e.g. "machine learning") match if all their tokens
    appear adjacently in the topic text.
    """
    import re

    matched: set[str] = set()
    haystack = " ".join(t.lower() for t in topics)
    # Tokenize once: words and hyphenated terms.
    tokens = set(re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)?", haystack))

    for cluster, aliases in CLUSTER_ALIASES.items():
        cluster_label = cluster.replace("_", " ")
        # The cluster's own label is multi-word — check substring (safe, it's long).
        candidates = [(cluster_label, False)] + [(a, len(a.split()) == 1) for a in aliases]
        for kw, is_single_token in candidates:
            if is_single_token:
                # Short single-word alias: match on token boundary only.
                if kw in tokens:
                    matched.add(cluster)
                    break
            else:
                # Multi-word or the cluster label: substring match is safe.
                if kw in haystack:
                    matched.add(cluster)
                    break
    return matched


def get_starter_sources(topics: list[str], max_sources: int = 8) -> list[dict]:
    """Return a deduplicated list of starter sources for the matched clusters.

    Capped at max_sources so a new user isn't flooded; ingestion picks up new
    posts on the next scheduled fetch. Clusters are sorted before iteration so
    the cap is deterministic across process restarts (Python set ordering is
    randomized per process via hash seed).
    """
    clusters = sorted(match_clusters(topics))
    seen_urls: set[str] = set()
    out: list[dict] = []
    for cluster in clusters:
        for src in STARTER_SOURCES.get(cluster, []):
            if src["url"] in seen_urls:
                continue
            seen_urls.add(src["url"])
            out.append(src)
            if len(out) >= max_sources:
                return out
    return out
