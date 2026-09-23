"""OpenAI-compatible chat client.

Model ids, the base URL, and the API key come from settings (`LLM_BASE_URL`,
`LLM_API_KEY`, `LLM_MODEL_PRIMARY`, `LLM_MODEL_FAST`). Nothing in this module
names a model. A 404 / model-not-found response opens a circuit breaker so a
retired model is not retried on every item. Rate limits use a token bucket
sized to the provider's TPM/RPM. Digest generation must not depend on this
client succeeding — callers fall back to extractive summaries.
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

PROMPT_VERSION = "summarize-v1"
_MAX_ATTEMPTS = 3

Clock = Callable[[], float]
Sleeper = Callable[[float], Awaitable[None]]


class TokenBucket:
    """Per-minute token and request bucket. `clock` and `sleep` are injectable."""

    def __init__(
        self,
        tpm: int,
        rpm: int,
        *,
        clock: Clock = time.monotonic,
        sleep: Sleeper = asyncio.sleep,
    ) -> None:
        self.tpm = max(1, tpm)
        self.rpm = max(1, rpm)
        self._clock = clock
        self._sleep = sleep
        self._tokens = float(self.tpm)
        self._requests = float(self.rpm)
        self._updated = self._clock()

    def _refill(self) -> None:
        now = self._clock()
        elapsed = max(0.0, now - self._updated)
        self._updated = now
        self._tokens = min(float(self.tpm), self._tokens + elapsed * (self.tpm / 60.0))
        self._requests = min(float(self.rpm), self._requests + elapsed * (self.rpm / 60.0))

    async def acquire(self, tokens: int) -> None:
        needed = float(max(1, tokens))
        while True:
            self._refill()
            if self._tokens >= needed and self._requests >= 1.0:
                self._tokens -= needed
                self._requests -= 1.0
                return
            token_wait = (
                0.0 if self._tokens >= needed else (needed - self._tokens) * 60.0 / self.tpm
            )
            req_wait = 0.0 if self._requests >= 1.0 else (1.0 - self._requests) * 60.0 / self.rpm
            await self._sleep(max(token_wait, req_wait, 0.01))


def _is_model_missing(status_code: int, body: str) -> bool:
    if status_code == 404:
        return True
    lowered = body.lower()
    if "model" not in lowered:
        return False
    return any(
        phrase in lowered
        for phrase in ("not found", "does not exist", "decommissioned", "unknown model", "no such")
    )


class LLMClient:
    """One OpenAI-compatible endpoint. Construct a second instance for a fallback provider."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Sleeper = asyncio.sleep,
        clock: Clock = time.monotonic,
        tpm: int | None = None,
        rpm: int | None = None,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url if base_url is not None else settings.llm_base_url).rstrip("/")
        self._api_key_override = api_key
        self._transport = transport
        self._sleep = sleep
        self._bucket = TokenBucket(
            tpm if tpm is not None else settings.llm_tpm_limit,
            rpm if rpm is not None else settings.llm_rpm_limit,
            clock=clock,
            sleep=sleep,
        )
        self._circuit_open = False
        self._circuit_reason = ""

    @property
    def api_key(self) -> str:
        if self._api_key_override is not None:
            return self._api_key_override
        return get_settings().llm_api_key

    @property
    def circuit_open(self) -> bool:
        return self._circuit_open

    def reset_circuit(self) -> None:
        self._circuit_open = False
        self._circuit_reason = ""

    def _trip(self, model: str, body: str) -> None:
        self._circuit_open = True
        self._circuit_reason = (
            f"LLM model {model!r} was rejected by {self.base_url}. "
            "Update LLM_MODEL_PRIMARY and LLM_MODEL_FAST to a model the provider "
            "still serves (Groq defaults: openai/gpt-oss-120b and openai/gpt-oss-20b). "
            f"Provider said: {body[:300]}"
        )
        logger.error(self._circuit_reason)

    async def _backoff(self, attempt: int, retry_after: str | None) -> None:
        if retry_after:
            try:
                delay = float(retry_after)
            except ValueError:
                delay = 0.0
        else:
            delay = 0.0
        if delay <= 0:
            delay = min(20.0, float(2**attempt)) + random.random()
        await self._sleep(delay)

    async def _post(self, payload: dict[str, Any]) -> httpx.Response:
        timeout = httpx.Timeout(get_settings().llm_timeout_seconds)
        async with httpx.AsyncClient(transport=self._transport, timeout=timeout) as client:
            return await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

    async def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int = 1024,
        temperature: float = 0.1,
        json_mode: bool = False,
    ) -> str | None:
        """Return assistant text, or None when the provider cannot answer.

        None covers: no API key, an open circuit, a retired model, and a
        provider that is still failing after retries. Callers must tolerate it.
        """
        if not self.api_key:
            return None
        if self._circuit_open:
            logger.error("LLM circuit open: %s", self._circuit_reason)
            return None

        estimate = max(1, sum(len(m.get("content", "")) for m in messages) // 4 + max_tokens)
        await self._bucket.acquire(estimate)
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        last_status: int | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                resp = await self._post(payload)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                logger.warning("LLM transport error (attempt %s): %s", attempt + 1, e)
                if attempt + 1 == _MAX_ATTEMPTS:
                    return None
                await self._backoff(attempt, None)
                continue

            if resp.status_code == 200:
                try:
                    data = resp.json()
                    return str(data["choices"][0]["message"].get("content") or "")
                except (KeyError, IndexError, TypeError, ValueError) as e:
                    logger.warning("LLM response was not a chat completion: %s", e)
                    return None

            body = resp.text[:500]
            if _is_model_missing(resp.status_code, body):
                self._trip(model, body)
                return None
            if resp.status_code == 429 or resp.status_code >= 500:
                last_status = resp.status_code
                logger.warning("LLM HTTP %s (attempt %s)", resp.status_code, attempt + 1)
                if attempt + 1 == _MAX_ATTEMPTS:
                    return None
                await self._backoff(attempt, resp.headers.get("retry-after"))
                continue
            logger.error("LLM request failed with HTTP %s: %s", resp.status_code, body)
            return None
        logger.error("LLM request failed after retries (last HTTP %s)", last_status)
        return None

    async def complete_json(
        self,
        *,
        model: str,
        system: str,
        user: str,
        max_tokens: int = 1024,
    ) -> dict[str, Any] | None:
        """Return a JSON object. One repair attempt if the first reply is not JSON."""
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        raw = await self.complete(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.1,
            json_mode=True,
        )
        parsed = _parse_json_object(raw) if raw else None
        if parsed is not None or raw is None or self._circuit_open or not self.api_key:
            return parsed

        repair = await self.complete(
            model=model,
            messages=[
                *messages,
                {"role": "assistant", "content": raw},
                {
                    "role": "user",
                    "content": "That was not valid JSON. Return only one JSON object, no markdown.",
                },
            ],
            max_tokens=max_tokens,
            temperature=0.0,
            json_mode=True,
        )
        return _parse_json_object(repair) if repair else None


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    clean = raw.strip()
    if clean.startswith("```"):
        parts = clean.split("```")
        clean = parts[1] if len(parts) > 1 else clean
        if clean.startswith("json"):
            clean = clean[4:]
        clean = clean.strip()
    try:
        data = json.loads(clean)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict):
        return data
    return None
