"""Offline extraction corpus. Pages are generated here and are not third-party copies.

``make extract-eval`` prints snippet recall and word-level F1. Article pages
are the ones the gate measures. Listing pages are present so the cascade can
refuse them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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


# --------------------------------------------------------------- real pages
# Real published pages with ground truth from each post's own Markdown source
# (#230); collected by scripts/collect_real_pages.py, licences in the manifest.
REAL_PAGES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "real_pages"


def _words(text: str) -> set[str]:
    import re

    return set(re.findall(r"[a-z0-9]+", text.lower()))


def evaluate_real(root: Path = REAL_PAGES) -> dict:
    """Word precision, recall and F1 per source over the real-page fixtures."""
    import gzip
    import json

    per_source: dict[str, list[tuple[float, float, float]]] = {}
    for page in json.loads((root / "manifest.json").read_text()):
        html = gzip.decompress((root / f"{page['id']}.html.gz").read_bytes()).decode()
        expected = _words(gzip.decompress((root / f"{page['id']}.txt.gz").read_bytes()).decode())
        got = _words(extract_html(html, page["url"]).text)
        overlap = len(expected & got)
        precision = overlap / len(got) if got else 0.0
        recall = overlap / len(expected) if expected else 1.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_source.setdefault(page["source"], []).append((precision, recall, f1))

    def summary(rows: list[tuple[float, float, float]]) -> dict:
        n = len(rows)
        return {
            "pages": n,
            "precision": sum(r[0] for r in rows) / n,
            "recall": sum(r[1] for r in rows) / n,
            "word_f1": sum(r[2] for r in rows) / n,
        }

    every = [row for rows in per_source.values() for row in rows]
    return {"overall": summary(every), "by_source": {s: summary(r) for s, r in per_source.items()}}
