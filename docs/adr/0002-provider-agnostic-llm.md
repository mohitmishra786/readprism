# ADR 0002 — One OpenAI-compatible LLM client

- **Status:** Accepted
- **Date:** 2026-09-24
- **Context tags:** llm, groq, reliability

## Context

Summaries called Groq with `llama-3.3-70b-versatile` and `llama-3.1-8b-instant`.
Groq removed both from the free and developer tiers on 2026-08-16. A second
client hard-coded `gpt-4o-mini`. The digest builder calls the summarizer, so a
dead model can fail every summary. Decisions D-01 and D-02 require a
provider-agnostic client and an extractive fallback.

## Options

1. Keep the Groq SDK and only change the default model id. The next deprecation
   breaks every call site again, and the SDK is not the OpenAI-compatible shape
   other providers share.
2. One HTTP client that posts to `{LLM_BASE_URL}/chat/completions`, with model
   ids only in settings, a token bucket, a circuit breaker on model-not-found,
   and an extractive summary when the call does not return JSON.

## Decision

Option 2. Defaults on Groq are `openai/gpt-oss-120b` (primary) and
`openai/gpt-oss-20b` (fast). Legacy `GROQ_*` variables still work. The two
retired ids are rewritten with a warning. `summary_source` on each item is
`llm` or `extractive`.

## Consequences

- The digest builds with `LLM_API_KEY` unset.
- Operators point the same client at Ollama, OpenRouter, or OpenAI by changing
  the base URL, key, and model.
- The `groq` and `openai` Python SDKs are no longer on the request path. The
  `groq` package remains in `requirements.txt` until a later cleanup so this
  change does not also reshuffle the image's dependency set.
- Cache keys include the prompt version and the model, so a model change does
  not serve a stale summary.
