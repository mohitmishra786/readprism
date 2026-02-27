from __future__ import annotations

import json
from typing import Optional

from app.config import get_settings
from app.services.summarization.groq_client import (
    SummarizationResult,
    _USER_PROMPT_TEMPLATE,
    _SYSTEM_PROMPT,
    _parse_result,
    _truncate_text,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class OpenAISummarizer:
    """Fallback summarizer using OpenAI. Only instantiated when
    settings.openai_fallback_enabled is True and Groq has failed."""

    def __init__(self) -> None:
        import openai
        self._client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

    async def summarize(self, title: str, full_text: str) -> Optional[SummarizationResult]:
        content = _truncate_text(full_text)
        prompt = _USER_PROMPT_TEMPLATE.format(title=title, content=content)

        for attempt in range(2):
            try:
                temperature = 0.1 if attempt == 0 else 0.0
                response = await self._client.chat.completions.create(
                    model="gpt-4o-mini",
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
                logger.error(f"OpenAI summarization attempt {attempt + 1} failed: {e}")
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
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=256,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"OpenAI topic synthesis failed: {e}")
            return ""
