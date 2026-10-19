"""Extraction on real published pages (#230).

Ground truth is each post's own Markdown source, so nothing is hand-labelled.
Blog posts are gated at F1 >= 0.95. Wikipedia is gated at 0.90: its data
tables are content the reader keeps, but the plain-text ground truth leaves
them out (#319 removed the reference lists that used to drag it to 0.77).
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


def test_wikipedia_without_its_reference_lists(report):
    assert report["by_source"]["wikipedia"]["word_f1"] >= 0.90


def test_overall_real_page_f1(report):
    assert report["overall"]["word_f1"] >= 0.95


def test_citations_go_but_blog_footnotes_and_tables_stay():
    """#319: only MediaWiki's citation apparatus is removed."""
    from app.services.ingestion.extract import extract_html

    prose = " ".join(f"Sentence {i} about compilers and loop lowering." for i in range(40))
    wiki = (
        f"<html><body><main><p>{prose}<sup class='reference'>[1]</sup></p>"
        "<div class='mw-references-wrap'><ol class='references'>"
        "<li>Smith, J. (2019). Retrieved 2024-01-01. doi:10.1000/xyz123</li></ol></div>"
        "</main></body></html>"
    )
    text = extract_html(wiki, "https://en.wikipedia.org/wiki/X").text
    assert "Sentence 39" in text and "doi" not in text and "[1]" not in text

    blog = (
        f"<html><body><article><p>{prose}<sup id='fnref:1'><a href='#fn:1'>1</a></sup></p>"
        "<table><tr><th>Pass</th><th>Speed-up</th></tr><tr><td>unrolling</td><td>1.8x</td></tr></table>"
        "<div class='footnotes' role='doc-endnotes'><ol><li id='fn:1'>Measured on an M4 laptop.</li></ol></div>"
        "</article></body></html>"
    )
    text = extract_html(blog, "https://blog.example/post").text
    assert "unrolling" in text and "Measured on an M4 laptop" in text
