from __future__ import annotations

import json

from app.config import get_settings
from app.services.llm.client import LLMClient
from app.utils.logging import get_logger

logger = get_logger(__name__)


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
        summary_source: str = "llm",
    ) -> None:
        self.headline = headline
        self.brief = brief
        self.detailed = detailed
        self.depth_score = depth_score
        self.is_original_reporting = is_original_reporting
        self.has_citations = has_citations
        self.topic_clusters = topic_clusters
        self.reading_time_minutes = reading_time_minutes
        self.summary_source = summary_source


_SYSTEM_PROMPT = (
    "You are a precise content analyst. Return only valid JSON. No markdown, no explanation."
)

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


def _parse_result(raw: str) -> SummarizationResult | None:
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
    """Historical name. Talks to whatever OpenAI-compatible endpoint is configured."""

    def __init__(self, llm: LLMClient | None = None) -> None:
        self._llm_client = llm
        self._fallback_client: LLMClient | None = None

    def _llm(self) -> LLMClient:
        if self._llm_client is None:
            self._llm_client = LLMClient()
        return self._llm_client

    async def summarize(self, title: str, full_text: str) -> SummarizationResult | None:
        content = _truncate_text(full_text)
        prompt = _USER_PROMPT_TEMPLATE.format(title=title, content=content)
        current = get_settings()
        data = await self._llm().complete_json(
            model=current.llm_model_primary,
            system=_SYSTEM_PROMPT,
            user=prompt,
            max_tokens=1024,
        )
        if (
            data is None
            and current.openai_fallback_enabled
            and current.openai_api_key
            and current.openai_model
        ):
            if self._fallback_client is None:
                self._fallback_client = LLMClient(
                    base_url=current.openai_base_url,
                    api_key=current.openai_api_key,
                )
            fallback = self._fallback_client
            data = await fallback.complete_json(
                model=current.openai_model,
                system=_SYSTEM_PROMPT,
                user=prompt,
                max_tokens=1024,
            )
        if not data:
            return None
        result = _parse_result_data(data)
        if result is not None:
            result.summary_source = "llm"
        return result

    async def synthesize_topic(self, items: list[SummarizationResult], topic: str) -> str:
        briefs = "\n\n".join([f"- {item.brief}" for item in items[:5]])
        prompt = (
            f"Given these summaries of articles about {topic}, write a single 3-4 sentence briefing "
            f"that captures what happened, the key disagreements or different angles between sources, "
            f"and what a reader should know. Return only the briefing text.\n\n{briefs}"
        )
        text = await self._llm().complete(
            model=get_settings().llm_model_primary,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=256,
        )
        return text or ""

    async def extract_topics(self, text: str) -> list[str]:
        prompt = (
            "Extract 5-10 specific topic labels from this text. "
            'Return a JSON object {"topics": ["..."]}. Be specific, not generic.\n\n'
            f"{text[:2000]}"
        )
        data = await self._llm().complete_json(
            model=get_settings().llm_model_fast,
            system="Return only a JSON object with a topics array of strings.",
            user=prompt,
            max_tokens=256,
        )
        if not data:
            return []
        topics = data.get("topics", [])
        if not isinstance(topics, list):
            return []
        return [str(topic) for topic in topics if isinstance(topic, str) and topic.strip()]


def _parse_result_data(data: dict) -> SummarizationResult | None:
    try:
        return SummarizationResult(
            headline=str(data.get("headline", "")),
            brief=str(data.get("brief", "")),
            detailed=str(data.get("detailed", "")),
            depth_score=float(data.get("depth_score", 0.5)),
            is_original_reporting=bool(data.get("is_original_reporting", False)),
            has_citations=bool(data.get("has_citations", False)),
            topic_clusters=[str(t) for t in data.get("topic_clusters", [])],
            reading_time_minutes=int(data.get("reading_time_minutes", 5)),
            summary_source="llm",
        )
    except (KeyError, TypeError, ValueError) as e:
        logger.warning(f"Failed to parse summarization JSON: {e}")
        return None
