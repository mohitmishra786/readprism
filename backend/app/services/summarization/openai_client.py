"""The OpenAI SDK fallback used to live here and hard-coded a model id.

Fallback calls now go through `LLMClient` (see `GroqSummarizer.summarize`)
using `OPENAI_BASE_URL`, `OPENAI_API_KEY`, and `OPENAI_MODEL`. This module
remains so old import paths fail loudly instead of calling a retired client.
"""

from __future__ import annotations


class OpenAISummarizer:
    def __init__(self) -> None:
        raise RuntimeError(
            "OpenAISummarizer was removed. Configure OPENAI_MODEL and "
            "OPENAI_FALLBACK_ENABLED; GroqSummarizer uses LLMClient for fallback."
        )
