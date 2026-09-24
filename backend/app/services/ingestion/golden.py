"""Offline extraction corpus. Pages are generated here and are not third-party copies.

``make extract-eval`` prints snippet recall and word-level F1. Article pages
are the ones the gate measures. Listing pages are present so the cascade can
refuse them.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.ingestion.extract import extract_html

ARTICLE_COUNT = 80
LISTING_COUNT = 20


@dataclass
class CorpusPage:
    url: str
    html: str
    snippet: str
    expected_text: str
    kind: str


def build_corpus() -> list[CorpusPage]:
    pages: list[CorpusPage] = []
    for index in range(ARTICLE_COUNT):
        snippet = f"Snippet {index} records prism topic {index % 7} for the golden check."
        body = " ".join(f"bodyword{index}x{n}" for n in range(30))
        expected = f"{snippet} {body}"
        html = (
            '<!doctype html><html lang="en"><head><title>Article '
            f"{index}</title></head><body><article><p>{snippet}</p><p>{body}</p></article></body></html>"
        )
        pages.append(
            CorpusPage(
                url=f"https://fixtures.example/article/{index}",
                html=html,
                snippet=snippet,
                expected_text=expected,
                kind="article",
            )
        )
    for index in range(LISTING_COUNT):
        cards = "".join(
            f'<article><h2>Card {index}-{n}</h2><a href="/c/{n}">link</a></article>'
            for n in range(4)
        )
        html = f'<!doctype html><html><body class="listing">{cards}</body></html>'
        pages.append(
            CorpusPage(
                url=f"https://fixtures.example/list/{index}",
                html=html,
                snippet="",
                expected_text="",
                kind="listing",
            )
        )
    return pages


def word_f1(expected: str, extracted: str) -> float:
    exp = set(expected.lower().split())
    got = set(extracted.lower().split())
    if not exp and not got:
        return 1.0
    if not exp or not got:
        return 0.0
    overlap = len(exp & got)
    precision = overlap / len(got)
    recall = overlap / len(exp)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def snippet_recall(snippet: str, extracted: str) -> float:
    exp = snippet.lower().split()
    if not exp:
        return 1.0
    blob = extracted.lower()
    return sum(1 for word in exp if word in blob.split()) / len(exp)


def evaluate() -> dict:
    f1_scores: list[float] = []
    recalls: list[float] = []
    methods: set[str] = set()
    listings_unrankable = 0
    for page in build_corpus():
        result = extract_html(page.html, page.url)
        if page.kind == "listing":
            if not result.rankable:
                listings_unrankable += 1
            continue
        f1_scores.append(word_f1(page.expected_text, result.text))
        recalls.append(snippet_recall(page.snippet, result.text))
        methods.add(result.method)
    count = len(f1_scores) or 1
    return {
        "articles": len(f1_scores),
        "listings": LISTING_COUNT,
        "listings_unrankable": listings_unrankable,
        "word_f1": sum(f1_scores) / count,
        "snippet_recall": sum(recalls) / count,
        "methods": sorted(methods),
    }
