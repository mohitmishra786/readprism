from __future__ import annotations

import json
from typing import Optional

import groq

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class SummarizationResult:
    def __init__(
        self,
        headline: str,
        brief: str,
        detailed: str,
        depth_score: float,
        is_original_reporting: bool,
        has_citations: bool,
        topic_clusters: list[str],
        reading_time_minutes: int,
    ) -> None:
        self.headline = headline
        self.brief = brief
        self.detailed = detailed
        self.depth_score = depth_score
        self.is_original_reporting = is_original_reporting
        self.has_citations = has_citations
        self.topic_clusters = topic_clusters
        self.reading_time_minutes = reading_time_minutes


_SYSTEM_PROMPT = "You are a precise content analyst. Return only valid JSON. No markdown, no explanation."

_USER_PROMPT_TEMPLATE = """Analyze this article and return a JSON object with exactly these keys:
- "headline": one sentence, max 15 words, captures the core claim
- "brief": 2-3 sentences summarizing the main argument and key facts
- "detailed": one paragraph (4-6 sentences) with key takeaways for a sophisticated reader
- "depth_score": float 0.0-1.0 where 1.0 is deeply original research and 0.0 is shallow aggregation
- "is_original_reporting": boolean
- "has_citations": boolean
- "topic_clusters": list of 1-5 specific topic labels (e.g. "distributed consensus", "rust programming language", "urban housing policy")
- "reading_time_minutes": estimated integer

Title: {title}
Content: {content}"""


def _truncate_text(text: str, max_chars: int = 16000) -> str:
    """Approx 4000 tokens at ~4 chars/token."""
    return text[:max_chars]


def _parse_result(raw: str) -> Optional[SummarizationResult]:
    try:
        # Strip any markdown fences if present
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        data = json.loads(clean)
        return SummarizationResult(
            headline=data.get("headline", ""),
            brief=data.get("brief", ""),
            detailed=data.get("detailed", ""),
            depth_score=float(data.get("depth_score", 0.5)),
            is_original_reporting=bool(data.get("is_original_reporting", False)),
            has_citations=bool(data.get("has_citations", False)),
            topic_clusters=list(data.get("topic_clusters", [])),
            reading_time_minutes=int(data.get("reading_time_minutes", 5)),
        )
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning(f"Failed to parse summarization JSON: {e}")
        return None


class GroqSummarizer:
    def __init__(self) -> None:
        self._client = groq.AsyncGroq(api_key=settings.groq_api_key)

    async def summarize(self, title: str, full_text: str) -> Optional[SummarizationResult]:
        content = _truncate_text(full_text)
        prompt = _USER_PROMPT_TEMPLATE.format(title=title, content=content)

        for attempt in range(2):
            try:
                temperature = 0.1 if attempt == 0 else 0.0
                response = await self._client.chat.completions.create(
                    model=settings.groq_summarization_model,
                    messages=[
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=temperature,
                    max_tokens=1024,
                )
                raw = response.choices[0].message.content or ""
                result = _parse_result(raw)
                if result:
                    return result
            except Exception as e:
                logger.error(f"Groq summarization attempt {attempt + 1} failed: {e}")
                if attempt == 1:
                    return None
        return None

    async def synthesize_topic(self, items: list[SummarizationResult], topic: str) -> str:
        briefs = "\n\n".join([f"- {item.brief}" for item in items[:5]])
        prompt = (
            f"Given these summaries of articles about {topic}, write a single 3-4 sentence briefing "
            f"that captures what happened, the key disagreements or different angles between sources, "
            f"and what a reader should know. Return only the briefing text.\n\n{briefs}"
        )
        try:
            response = await self._client.chat.completions.create(
                model=settings.groq_summarization_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=256,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"Groq topic synthesis failed: {e}")
            return ""

    async def extract_topics(self, text: str) -> list[str]:
        prompt = f"Extract 5-10 specific topic labels from this text. Return as JSON array of strings. Be specific, not generic.\n\n{text[:2000]}"
        try:
            response = await self._client.chat.completions.create(
                model=settings.groq_fast_model,
                messages=[
                    {"role": "system", "content": "Return only a valid JSON array of strings."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=256,
            )
            raw = response.choices[0].message.content or "[]"
            clean = raw.strip()
            if clean.startswith("```"):
                lines = clean.split("\n")
                clean = "\n".join(lines[1:-1])
            return json.loads(clean)
        except Exception as e:
            logger.error(f"Groq topic extraction failed: {e}")
            return []
