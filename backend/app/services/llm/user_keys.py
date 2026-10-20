"""Readers' own LLM keys on hosted (#255).

A reader can add a key for an OpenAI-compatible provider from a fixed list
(BYOK_ALLOWED_BASE_URLS). It is encrypted at rest with a key derived from
SECRETS_ENCRYPTION_KEY (not SECRET_KEY), never returned by the API and never
logged; only its last 4 characters are shown. It is used only for that
reader's summaries (their digest items and the items they open), with no
fallback to the instance's key, and those summaries don't count against the
plan's AI allowance.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.llm_key import UserLLMKey
from app.services.llm.client import LLMClient
from app.utils import secretbox

PURPOSE = "user-llm-key"


def available() -> bool:
    return get_settings().deployment_mode == "hosted" and secretbox.configured()


def allowed_base_urls() -> list[str]:
    raw = get_settings().byok_allowed_base_urls
    return [u.strip().rstrip("/") for u in raw.split(",") if u.strip()]


def status(row: UserLLMKey | None) -> dict:
    if row is None:
        return {"configured": False, "base_url": None, "model": None, "last4": None}
    return {
        "configured": True,
        "base_url": row.base_url,
        "model": row.model,
        "last4": row.key_last4,
    }


async def get(session: AsyncSession, user_id: uuid.UUID) -> UserLLMKey | None:
    return await session.get(UserLLMKey, user_id)


async def save(
    session: AsyncSession, user_id: uuid.UUID, *, api_key: str, base_url: str, model: str | None
) -> UserLLMKey:
    row = await get(session, user_id) or UserLLMKey(user_id=user_id)
    row.base_url = base_url.rstrip("/")
    row.key_encrypted = secretbox.encrypt(api_key, purpose=PURPOSE)
    row.key_last4 = secretbox.last4(api_key)
    row.model = model or None
    session.add(row)
    await session.flush()
    return row


def client_for(row: UserLLMKey) -> tuple[LLMClient, str]:
    """(client, summary model) for a reader's key."""
    api_key = secretbox.decrypt(row.key_encrypted, purpose=PURPOSE)
    return LLMClient(base_url=row.base_url, api_key=api_key), row.model or get_settings().model_for(
        "summary"
    )


async def summarizer_for(session: AsyncSession, user_id: uuid.UUID):
    """An LLMSummarizer on the reader's own key, or None (no key, or not hosted)."""
    if not available():
        return None
    row = await get(session, user_id)
    if row is None:
        return None
    from app.services.summarization.groq_client import LLMSummarizer

    try:
        client, model = client_for(row)
    except secretbox.InvalidToken:
        return None  # SECRETS_ENCRYPTION_KEY changed; the reader must add the key again
    return LLMSummarizer(llm=client, summary_model=model, use_fallback=False)


async def check(api_key: str, base_url: str, model: str | None) -> bool:
    """One tiny request to see that the key and model work."""
    client = LLMClient(base_url=base_url, api_key=api_key)
    reply = await client.complete(
        model=model or get_settings().model_for("summary"),
        messages=[{"role": "user", "content": "Reply with OK."}],
        max_tokens=5,
    )
    return reply is not None
