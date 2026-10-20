"""Hosted bring-your-own LLM key (#255)."""

from __future__ import annotations

import logging
import uuid
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models.llm_key import UserLLMKey
from app.models.user import User
from app.services import entitlements as ent
from app.services.llm import user_keys
from app.services.llm.client import LLMClient

KEY = "sk-test-0123456789abcdefWXYZ"
GROQ = "https://api.groq.com/openai/v1"


@pytest.fixture
def hosted(monkeypatch):
    s = get_settings()
    for key, value in {
        "deployment_mode": "hosted",
        "registration_mode": "open",
        "email_verification": "off",
        # Trial accounts: a paused one (no plan) can't change its key (#341).
        "billing_trial_days": 30,
        "secrets_encryption_key": "test-secrets-key-" + "x" * 32,
        "hosted_plan_quotas": {"trial": {"llm_summaries_per_day": 1}},
    }.items():
        monkeypatch.setattr(s, key, value)
    return s


async def _signup(client, db_session):
    email = f"k{uuid.uuid4().hex[:6]}@example.com"
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "TestPass123!", "accept_terms": True},
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    return user, headers


async def _put(client, headers, **body):
    payload = {"api_key": KEY, "base_url": GROQ, "model": "openai/gpt-oss-20b", **body}
    with patch.object(user_keys, "check", AsyncMock(return_value=True)):
        return await client.put("/api/v1/account/llm-key", json=payload, headers=headers)


@pytest.mark.asyncio
async def test_key_is_encrypted_never_returned_and_never_logged(client, db_session, hosted, caplog):
    user, headers = await _signup(client, db_session)
    caplog.set_level(logging.DEBUG)
    saved = await _put(client, headers)
    assert saved.status_code == 200
    assert saved.json() == {
        "configured": True,
        "base_url": GROQ,
        "model": "openai/gpt-oss-20b",
        "last4": "WXYZ",
    }
    shown = (await client.get("/api/v1/account/llm-key", headers=headers)).json()
    assert shown["last4"] == "WXYZ" and GROQ in shown["allowed_base_urls"]
    assert KEY not in saved.text + str(shown)

    uid = user.id
    row = await db_session.get(UserLLMKey, uid)
    assert KEY not in row.key_encrypted and row.key_encrypted.startswith("gAAAA")
    assert KEY not in caplog.text

    assert (await client.delete("/api/v1/account/llm-key", headers=headers)).status_code == 204
    db_session.expire_all()
    assert await db_session.get(UserLLMKey, uid) is None


@pytest.mark.asyncio
async def test_only_listed_providers_and_a_working_key(client, db_session, hosted):
    _, headers = await _signup(client, db_session)
    bad = await _put(client, headers, base_url="http://169.254.169.254/v1")
    assert bad.status_code == 422
    with patch.object(user_keys, "check", AsyncMock(return_value=False)):
        rejected = await client.put(
            "/api/v1/account/llm-key", json={"api_key": KEY, "base_url": GROQ}, headers=headers
        )
    assert rejected.status_code == 422 and "didn't accept" in rejected.json()["detail"]


@pytest.mark.asyncio
async def test_selfhost_and_no_encryption_key_have_no_byok(client, db_session, hosted, monkeypatch):
    _, headers = await _signup(client, db_session)
    monkeypatch.setattr(hosted, "secrets_encryption_key", "")
    assert (await client.get("/api/v1/account/llm-key", headers=headers)).status_code == 404
    monkeypatch.setattr(hosted, "secrets_encryption_key", "test-secrets-key-" + "x" * 32)
    monkeypatch.setattr(hosted, "deployment_mode", "selfhost")
    assert (await client.get("/api/v1/account/llm-key", headers=headers)).status_code == 404


@pytest.mark.asyncio
async def test_digest_summaries_use_the_readers_key_without_fallback_or_quota(
    client, db_session, hosted
):
    from app.services.digest.builder import summarize_placed

    user, headers = await _signup(client, db_session)
    await _put(client, headers, model="my-model")
    seen = {}

    async def fake_ensure(items, *, limit=None, summarizer=None):
        llm = summarizer._llm()
        seen.update(
            base=llm.base_url,
            key=llm.api_key,
            model=summarizer._summary_model,
            fallback=summarizer._use_fallback,
        )
        return 7

    with patch("app.services.summarization.lazy.ensure_llm_summaries", fake_ensure):
        assert await summarize_placed(user, [], db_session) == 7
    assert seen == {"base": GROQ, "key": KEY, "model": "my-model", "fallback": False}
    assert await ent.used_today(user.id, ent.LLM_SUMMARIES) == 0


@pytest.mark.asyncio
async def test_opened_item_runs_on_own_key_and_skips_the_quota(client, db_session, hosted):
    from app.api import content

    user, headers = await _signup(client, db_session)
    await _put(client, headers)
    item = type("I", (), {"id": uuid.uuid4()})()
    delay = AsyncMock()
    with (
        patch("app.services.summarization.lazy.needs_llm_summary", return_value=True),
        patch("app.workers.tasks.compute_embeddings.summarize_item_with_llm.delay", delay),
    ):
        for _ in range(3):  # past the free plan's 1 a day
            item.id = uuid.uuid4()
            await content._queue_llm_summary(item, user, db_session)
    assert delay.call_count == 3 and delay.call_args.args[1] == str(user.id)
    assert await ent.used_today(user.id, ent.LLM_SUMMARIES) == 0


@pytest.mark.asyncio
async def test_rotated_encryption_key_disables_the_stored_key(
    client, db_session, hosted, monkeypatch
):
    user, headers = await _signup(client, db_session)
    await _put(client, headers)
    monkeypatch.setattr(hosted, "secrets_encryption_key", "another-key-" + "y" * 32)
    assert await user_keys.summarizer_for(db_session, user.id) is None


@pytest.mark.asyncio
async def test_deleting_the_account_deletes_the_key(client, db_session, hosted):
    user, headers = await _signup(client, db_session)
    await _put(client, headers)
    uid = user.id
    with patch("app.utils.email.send_email", AsyncMock(return_value=True)):
        assert (await client.delete("/api/v1/account", headers=headers)).status_code == 204
    db_session.expire_all()
    assert await db_session.get(UserLLMKey, uid) is None


@pytest.mark.asyncio
async def test_provider_error_echoing_the_key_is_redacted(caplog):
    def handler(request):
        return httpx.Response(401, text=f"Incorrect API key provided: {KEY}")

    llm = LLMClient(base_url=GROQ, api_key=KEY, transport=httpx.MockTransport(handler))
    caplog.set_level(logging.ERROR)
    assert await llm.complete(model="m", messages=[{"role": "user", "content": "hi"}]) is None
    assert KEY not in caplog.text and "***" in caplog.text
