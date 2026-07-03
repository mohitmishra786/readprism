"""Tests for the starter-source cold-start pack."""
from __future__ import annotations

from app.services.cold_start.starter_sources import (
    get_starter_sources,
    match_clusters,
    STARTER_SOURCES,
)


def test_match_clusters_by_direct_keyword():
    """A topic containing a cluster keyword matches that cluster."""
    assert "ai" in match_clusters(["machine learning", "ai research"])
    assert "machine_learning" in match_clusters(["machine learning"])


def test_match_clusters_by_alias():
    """Aliases (e.g. 'llm' → ai, 'product management' → product) match."""
    assert "ai" in match_clusters(["working with llms"])
    assert "product" in match_clusters(["product management", "roadmaps"])
    assert "security" in match_clusters(["cryptography", "infosec"])


def test_match_clusters_is_case_insensitive():
    """Topic casing doesn't affect matching."""
    assert "ai" in match_clusters(["Artificial Intelligence"])
    assert "business" in match_clusters(["BUSINESS STRATEGY"])


def test_match_clusters_unrelated_topics_returns_empty():
    """Topics with no cluster match return an empty set."""
    assert match_clusters(["cooking", "gardening", "travel"]) == set()


def test_get_starter_sources_returns_feeds_for_matched_cluster():
    """Matched clusters yield seed sources with the expected fields."""
    sources = get_starter_sources(["artificial intelligence", "llms"])
    assert len(sources) > 0
    for s in sources:
        assert "name" in s and "url" in s and "feed_url" in s
        assert s["feed_url"].startswith("http")


def test_get_starter_sources_dedupes_across_clusters():
    """A source appearing in multiple clusters is returned only once."""
    sources = get_starter_sources(["technology", "programming", "ai"])
    urls = [s["url"] for s in sources]
    assert len(urls) == len(set(urls)), "duplicate seed sources returned"


def test_get_starter_sources_respects_max():
    """The max_sources cap is honored."""
    sources = get_starter_sources(
        ["technology", "ai", "programming", "startups", "business", "science", "design", "security"],
        max_sources=3,
    )
    assert len(sources) <= 3


def test_get_starter_sources_empty_for_no_match():
    """Unmatched topics yield no seeds."""
    assert get_starter_sources(["cooking", "travel"]) == []


def test_every_cluster_has_at_least_one_source():
    """Sanity: each defined cluster maps to at least one seed feed."""
    for cluster in STARTER_SOURCES:
        assert len(STARTER_SOURCES[cluster]) >= 1, f"{cluster} has no seed sources"
