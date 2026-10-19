"""Extraction on real published pages (#230).

Ground truth is each post's own Markdown source, so nothing is hand-labelled.
Blog posts are gated on F1; Wikipedia is gated on recall only, because the
extractor keeps reference lists and data tables there (precision ~0.64,
tracked as a known gap in docs/benchmarks.md).
"""

from __future__ import annotations

import json

import pytest

from app.services.ingestion.golden import REAL_PAGES, evaluate_real


@pytest.fixture(scope="module")
def report() -> dict:
    return evaluate_real()


def test_fixtures_carry_licence_and_source(report):
    manifest = json.loads((REAL_PAGES / "manifest.json").read_text())
    assert len(manifest) >= 50
    assert all(p["license"] and p["url"].startswith("https://") for p in manifest)
    assert report["overall"]["pages"] == len(manifest)


@pytest.mark.parametrize("source", ["go", "rust", "kubernetes"])
def test_blog_posts_extract_cleanly(report, source):
    assert report["by_source"][source]["word_f1"] >= 0.95


def test_no_real_page_loses_its_text(report):
    for source, row in report["by_source"].items():
        assert row["recall"] >= 0.95, source


def test_overall_real_page_f1(report):
    assert report["overall"]["word_f1"] >= 0.90
