"""Cross-tenant access suite (#167).

User A owns one of everything; user B tries every id-bearing route with A's
ids and reads every list endpoint. B must never see or change A's objects.

Every OpenAPI operation must be classified below. A new route that is not
listed fails `test_every_route_is_classified`, forcing whoever adds it to
decide how its isolation is tested.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from app.main import app
from app.models.api_token import ApiToken
from app.models.content import ContentItem, UserContentInteraction
from app.models.creator import Creator
from app.models.digest import Digest, DigestFeedbackPrompt, DigestItem
from app.models.interest_graph import InterestNode
from app.models.source import Source
from app.models.suggestion import SourceSuggestion
from app.models.user import User

MARK = f"ALPHASECRET{uuid.uuid4().hex[:8]}"

# Routes that take A's object ids. Body: a minimal valid payload so the request
# reaches the ownership check rather than failing validation.
ID_ROUTES: list[tuple[str, str, dict | None]] = [
    ("GET", "/api/v1/content/{private_content_id}", None),
    ("GET", "/api/v1/creators/{creator_id}", None),
    ("PUT", "/api/v1/creators/{creator_id}", {"priority": "high"}),
    ("DELETE", "/api/v1/creators/{creator_id}", None),
    ("GET", "/api/v1/creators/{creator_id}/summary", None),
    ("GET", "/api/v1/digest/{digest_id}", None),
    ("GET", "/api/v1/digest/{digest_id}/prompts", None),
    ("POST", "/api/v1/digest/{digest_id}/prompts/{prompt_id}/answer", {"answer": "x"}),
    ("POST", "/api/v1/digest/{digest_id}/prompts/{prompt_id}/dismiss", None),
    ("POST", "/api/v1/onboarding/calibration/{private_content_id}", {"rating": 1}),
    ("POST", "/api/v1/sources/discover-suggestions/{suggestion_id}/accept", None),
    ("POST", "/api/v1/sources/discover-suggestions/{suggestion_id}/dismiss", None),
    ("PUT", "/api/v1/sources/{source_id}", {"name": "pwned"}),
    ("DELETE", "/api/v1/sources/{source_id}", None),
    ("POST", "/api/v1/sources/{source_id}/fix", None),
    ("GET", "/api/v1/sources/import-jobs/{import_job_id}", None),
    ("GET", "/api/v1/search/why/{private_content_id}", None),
    ("DELETE", "/api/v1/tokens/{token_id}", None),
]

# Read endpoints whose response must not mention any of A's data.
LIST_ROUTES = [
    "/api/v1/account/export",
    "/api/v1/auth/me",
    "/api/v1/content/feed",
    "/api/v1/content/history",
    "/api/v1/content/saved",
    "/api/v1/creators",
    "/api/v1/digest/emerging",
    "/api/v1/digest/history",
    "/api/v1/integrations/logseq",
    "/api/v1/integrations/obsidian",
    "/api/v1/onboarding/calibration",
    "/api/v1/onboarding/first-digest/status",
    "/api/v1/preferences",
    "/api/v1/preferences/interest-graph",
    f"/api/v1/search?q={MARK}",  # checked on hits only (the query is echoed back)
    "/api/v1/sources",
    "/api/v1/sources/discover-suggestions",
    "/api/v1/sources/export-opml",
    "/api/v1/tokens",
]

# Not id-scoped to another user, or authorized by something other than the
# session; each with the reason.
EXEMPT = {
    (
        "GET",
        "/api/v1/feedback/interaction/{content_id}",
    ): "returns the caller's own interaction; checked below",
    ("GET", "/api/v1/digest/e/{action}/{item_id}"): "signed email link (HMAC over user+item)",
    ("POST", "/api/v1/digest/e/{action}/{item_id}"): "signed email link (HMAC over user+item)",
    ("GET", "/api/v1/digest/t/{action}"): "signed weekly-email topic link (HMAC over user+topic, #184)",
    ("POST", "/api/v1/digest/t/{action}"): "signed weekly-email topic link (HMAC over user+topic, #184)",
    ("GET", "/api/v1/digest/u/{action}"): "signed win-back link (HMAC over user+action, #238)",
    ("POST", "/api/v1/digest/u/{action}"): "signed win-back link (HMAC over user+action, #238)",
    ("POST", "/api/v1/newsletter/inbound/{provider}"): "provider webhook, signature-authenticated",
    ("POST", "/api/v1/billing/webhook/{provider_name}"): "MoR webhook, signature-authenticated",
    ("POST", "/api/v1/sources/starter-packs/{pack_id}/subscribe"): "public pack catalogue",
}


def _ops() -> set[tuple[str, str]]:
    return {(m.upper(), p) for p, ops in app.openapi()["paths"].items() for m in ops}


def _template(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "{}", path)


def test_every_route_is_classified():
    id_templates = {(m, _template(p)) for m, p, _ in ID_ROUTES}
    exempt_templates = {(m, _template(p)) for m, p in EXEMPT}
    unclassified = [
        (m, p)
        for m, p in sorted(_ops())
        if "{" in p and (m, _template(p)) not in id_templates | exempt_templates
    ]
    assert not unclassified, f"add these to ID_ROUTES or EXEMPT: {unclassified}"


async def _login(client: AsyncClient, email: str) -> dict:
    data = {"email": email, "password": "TestPass123!"}
    resp = await client.post("/api/v1/auth/register", json=data)
    client.cookies.clear()
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest_asyncio.fixture
async def tenants(client: AsyncClient, db_session):
    a_headers = await _login(client, f"a-{uuid.uuid4().hex[:6]}@example.com")
    b_headers = await _login(client, f"b-{uuid.uuid4().hex[:6]}@example.com")
    a = (
        (await db_session.execute(select(User).where(User.email.startswith("a-"))))
        .scalars()
        .first()
    )

    source = Source(user_id=a.id, url=f"https://{MARK.lower()}.example.com", name=MARK)
    creator = Creator(user_id=a.id, display_name=MARK)
    db_session.add_all([source, creator])
    await db_session.flush()
    private = ContentItem(
        url=f"https://{MARK.lower()}.example.com/private",
        title=f"{MARK} private newsletter",
        owner_user_id=a.id,
        origin="extension",
        fetched_at=datetime.now(UTC),
        topic_clusters=[MARK],
    )
    db_session.add(private)
    await db_session.flush()
    db_session.add(
        UserContentInteraction(
            user_id=a.id,
            content_item_id=private.id,
            saved=True,
            explicit_rating=1,
            opened_at=datetime.now(UTC),
        )
    )
    digest = Digest(user_id=a.id, total_items=1)
    db_session.add(digest)
    await db_session.flush()
    db_session.add(
        DigestItem(
            digest_id=digest.id,
            content_item_id=private.id,
            position=0,
            section="lead",
            prs_score=0.5,
            signal_breakdown={},
        )
    )
    prompt = DigestFeedbackPrompt(
        digest_id=digest.id, prompt_text=MARK, prompt_type="topic_accuracy"
    )
    token = ApiToken(
        user_id=a.id, name=MARK, token_hash=uuid.uuid4().hex * 2, prefix="rp_test", scopes=["read"]
    )
    suggestion = SourceSuggestion(
        user_id=a.id, url=f"https://{MARK.lower()}.example.net/feed", name=MARK, reason=MARK
    )
    node = InterestNode(user_id=a.id, topic_label=MARK, weight=0.9)
    db_session.add_all([prompt, token, suggestion, node])
    await db_session.commit()
    from app.workers.tasks.import_jobs import create_job

    import_job_id = await create_job(
        a.id, [{"url": f"https://{MARK.lower()}.example.org/f", "title": MARK}]
    )

    ids = {
        "import_job_id": import_job_id,
        "private_content_id": private.id,
        "creator_id": creator.id,
        "digest_id": digest.id,
        "prompt_id": prompt.id,
        "suggestion_id": suggestion.id,
        "source_id": source.id,
        "a_user_id": a.id,
        "token_id": token.id,
    }
    return {"a": a_headers, "b": b_headers, "ids": ids}


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "path", "body"), ID_ROUTES)
async def test_b_cannot_touch_a_objects_by_id(
    client: AsyncClient, tenants, db_session, method, path, body
):
    url = path.format(**{k: str(v) for k, v in tenants["ids"].items()})
    resp = await client.request(method, url, json=body, headers=tenants["b"])

    assert resp.status_code in (
        403,
        404,
    ), f"{method} {path} -> {resp.status_code}: {resp.text[:200]}"
    assert MARK not in resp.text


@pytest.mark.asyncio
async def test_a_objects_survive_b_attempts(client: AsyncClient, tenants, db_session):
    ids = tenants["ids"]
    for method, path, body in ID_ROUTES:
        url = path.format(**{k: str(v) for k, v in ids.items()})
        await client.request(method, url, json=body, headers=tenants["b"])
    db_session.expire_all()
    assert (await db_session.get(Source, ids["source_id"])).name == MARK
    assert await db_session.get(Creator, ids["creator_id"]) is not None
    token = await db_session.get(ApiToken, ids["token_id"])
    assert token is not None and token.revoked is False
    suggestion = await db_session.get(SourceSuggestion, ids["suggestion_id"])
    assert suggestion.status == "pending"


@pytest.mark.asyncio
@pytest.mark.parametrize("path", LIST_ROUTES)
async def test_b_list_endpoints_never_include_a_data(client: AsyncClient, tenants, path):
    resp = await client.get(path, headers=tenants["b"])
    assert resp.status_code < 500, f"{path} -> {resp.status_code}"
    text = resp.text
    if path.startswith("/api/v1/search"):
        text = str(resp.json().get("hits", []))
    assert MARK.lower() not in text.lower(), f"{path} leaked A's data"


@pytest.mark.asyncio
async def test_feedback_lookup_returns_only_the_callers_interaction(client: AsyncClient, tenants):
    url = f"/api/v1/feedback/interaction/{tenants['ids']['private_content_id']}"
    resp = await client.get(url, headers=tenants["b"])
    assert resp.status_code in (200, 403, 404)
    if resp.status_code == 200:
        body = resp.json()
        assert not body or (body.get("saved") is not True and body.get("explicit_rating") != 1)


@pytest.mark.asyncio
async def test_a_still_sees_own_objects(client: AsyncClient, tenants):
    """Sanity: the fixture is reachable by its owner, so 404s for B are meaningful."""
    ids = tenants["ids"]
    assert (
        await client.get(f"/api/v1/creators/{ids['creator_id']}", headers=tenants["a"])
    ).status_code == 200
    assert (
        await client.get(f"/api/v1/digest/{ids['digest_id']}", headers=tenants["a"])
    ).status_code == 200
    sources = (await client.get("/api/v1/sources", headers=tenants["a"])).text
    assert MARK in sources
