"""Extractive summary used whenever the LLM is missing, rate-limited, or broken.

Lead sentences plus a light overlap score against the title (a tiny TextRank
stand-in: sentences that share words with the title rank above pure position).
No network, no model. The digest can always ship one of these.
"""

from __future__ import annotations

import re

from app.services.summarization.groq_client import SummarizationResult

_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[a-z0-9']+")


def _sentences(text: str) -> list[str]:
    parts = [part.strip() for part in _SENTENCE.split(text.replace("\n", " ")) if part.strip()]
    return parts


def _tokens(text: str) -> set[str]:
    return {tok for tok in _WORD.findall(text.lower()) if len(tok) > 2}


def extractive_summary(title: str, full_text: str) -> SummarizationResult:
    sentences = _sentences(full_text) or ([title.strip()] if title.strip() else ["Untitled"])
    title_tokens = _tokens(title)
    ranked = sorted(
        range(len(sentences)),
        key=lambda i: (
            len(_tokens(sentences[i]) & title_tokens),
            -i,  # earlier sentences win ties
        ),
        reverse=True,
    )
    chosen = sorted(ranked[:6])
    ordered = [sentences[i] for i in chosen]
    brief = " ".join(ordered[:3])[:800]
    detailed = " ".join(ordered[:6])[:1600]
    words = len(full_text.split()) if full_text else len(title.split())
    reading_time = max(1, round(words / 230)) if words else 1
    headline = (title.strip() or sentences[0])[:180]
    return SummarizationResult(
        headline=headline,
        brief=brief or headline,
        detailed=detailed or brief or headline,
        depth_score=0.5,
        is_original_reporting=False,
        has_citations=False,
        topic_clusters=[],
        reading_time_minutes=reading_time,
        summary_source="extractive",
    )
