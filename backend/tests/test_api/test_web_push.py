"""Web Push digest alerts (#266)."""

from __future__ import annotations

import base64
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import select

from app.models.push import PushSubscription
from app.services import push


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _pub(key) -> bytes:
    return key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )


@pytest.fixture
def vapid(monkeypatch):
    from app.config import get_settings

    key = ec.generate_private_key(ec.SECP256R1())
    s = get_settings()
    monkeypatch.setattr(s, "vapid_public_key", b64(_pub(key)))
    monkeypatch.setattr(
        s, "vapid_private_key", b64(key.private_numbers().private_value.to_bytes(32, "big"))
    )
    monkeypatch.setattr(s, "vapid_subject", "mailto:ops@example.com")
    return key


def _device():
    """A browser's subscription keys (the receiving side)."""
    key = ec.generate_private_key(ec.SECP256R1())
    auth = b"0123456789abcdef"
    return key, b64(_pub(key)), b64(auth), auth


def _receiver_decrypt(body: bytes, ua_key, auth: bytes) -> bytes:
    """RFC 8291 / 8188 decryption, written independently of app.services.push."""
    salt, rs, idlen = body[:16], int.from_bytes(body[16:20], "big"), body[20]
    as_pub = body[21 : 21 + idlen]
    ciphertext = body[21 + idlen :]
    assert rs == 4096 and idlen == 65
    shared = ua_key.exchange(
        ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_pub)
    )

    def hkdf(s, ikm, info, n):
        return HKDF(algorithm=hashes.SHA256(), length=n, salt=s, info=info).derive(ikm)

    ikm = hkdf(auth, shared, b"WebPush: info\x00" + _pub(ua_key) + as_pub, 32)
    cek = hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    padded = AESGCM(cek).decrypt(nonce, ciphertext, None)
    assert padded.endswith(b"\x02")  # last-record delimiter
    return padded[:-1]


def test_encryption_round_trips_through_an_independent_receiver():
    ua_key, p256dh, auth_b64, auth = _device()
    message = json.dumps(push.digest_payload(12)).encode()
    body = push.encrypt(message, p256dh=p256dh, auth=auth_b64)
    assert _receiver_decrypt(body, ua_key, auth) == message
    # Fresh salt and server key per message.
    assert push.encrypt(message, p256dh=p256dh, auth=auth_b64)[:16] != body[:16]


def test_vapid_header_is_a_valid_es256_token_for_the_push_origin(vapid):
    headers = push.vapid_headers("https://fcm.googleapis.com/fcm/send/abc123")
    scheme, params = headers["Authorization"].split(" ", 1)
    fields = dict(part.strip().split("=", 1) for part in params.split(","))
    assert scheme == "vapid" and fields["k"] == b64(_pub(vapid))
    pem = vapid.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    claims = jwt.decode(
        fields["t"], pem, algorithms=["ES256"], audience="https://fcm.googleapis.com"
    )
    assert claims["sub"] == "mailto:ops@example.com"


async def _login(client):
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": f"wp{uuid.uuid4().hex[:6]}@example.com", "password": "TestPass123!"},
    )
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


def _sub_body(endpoint="https://push.example.com/send/xyz"):
    _, p256dh, auth_b64, _ = _device()
    return {"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth_b64}}


@pytest.mark.asyncio
async def test_push_is_off_without_vapid_keys(client):
    headers = await _login(client)
    assert (await client.get("/api/v1/push/public-key", headers=headers)).status_code == 404
    resp = await client.post("/api/v1/push/subscribe", json=_sub_body(), headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_subscribe_and_unsubscribe_only_your_own(client, db_session, vapid):
    a, b = await _login(client), await _login(client)
    assert (await client.get("/api/v1/push/public-key", headers=a)).json()["public_key"]
    body = _sub_body(f"https://push.example.com/send/{uuid.uuid4().hex}")
    with patch("app.services.push.endpoint_allowed", return_value=True):
        assert (
            await client.post("/api/v1/push/subscribe", json=body, headers=a)
        ).status_code == 201
    # Another user can't remove it.
    await client.post("/api/v1/push/unsubscribe", json={"endpoint": body["endpoint"]}, headers=b)
    rows = (
        (
            await db_session.execute(
                select(PushSubscription).where(PushSubscription.endpoint == body["endpoint"])
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    await client.post("/api/v1/push/unsubscribe", json={"endpoint": body["endpoint"]}, headers=a)
    db_session.expire_all()
    rows = (
        (
            await db_session.execute(
                select(PushSubscription).where(PushSubscription.endpoint == body["endpoint"])
            )
        )
        .scalars()
        .all()
    )
    assert rows == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint", ["http://push.example.com/x", "https://127.0.0.1/x", "https://10.0.0.5/x"]
)
async def test_non_public_endpoints_are_refused(client, vapid, endpoint):
    headers = await _login(client)
    resp = await client.post("/api/v1/push/subscribe", json=_sub_body(endpoint), headers=headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_notify_sends_prunes_gone_devices_and_counts_failures(db_session, vapid):
    from app.models.user import User

    user = User(email=f"n{uuid.uuid4().hex[:6]}@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    subs = []
    for name in ("ok", "gone", "error"):
        _, p256dh, auth_b64, _ = _device()
        sub = PushSubscription(
            user_id=user.id,
            endpoint=f"https://push.example.com/{name}/{uuid.uuid4().hex}",
            p256dh=p256dh,
            auth=auth_b64,
        )
        db_session.add(sub)
        subs.append(sub)
    await db_session.flush()

    async def fake_post(self, url, content, headers):
        assert headers["Content-Encoding"] == "aes128gcm" and headers["Authorization"].startswith(
            "vapid "
        )
        status_code = 201 if "/ok/" in url else 410 if "/gone/" in url else 500
        return MagicMock(status_code=status_code)

    with (
        patch("app.services.push.endpoint_allowed", return_value=True),
        patch("httpx.AsyncClient.post", fake_post),
    ):
        counts = await push.notify_user(db_session, user.id, push.digest_payload(5))
    assert counts == {"sent": 1, "gone": 1, "failed": 1}
    left = (
        (
            await db_session.execute(
                select(PushSubscription).where(PushSubscription.user_id == user.id)
            )
        )
        .scalars()
        .all()
    )
    assert {s.endpoint.split("/")[3] for s in left} == {"ok", "error"}
    assert next(s for s in left if "/error/" in s.endpoint).failure_count == 1


@pytest.mark.asyncio
async def test_a_built_digest_alerts_the_users_devices(db_session):
    from datetime import UTC, datetime

    from app.models.user import User
    from app.workers.tasks.build_digest import _build_digest_async
    from tests.conftest import TestingSessionLocal

    user = User(
        email=f"bd{uuid.uuid4().hex[:6]}@example.com", hashed_password="x", onboarding_complete=True
    )
    db_session.add(user)
    await db_session.commit()
    fake_digest = MagicMock(
        id=uuid.uuid4(), total_items=7, delivered_at=None, generated_at=datetime.now(UTC)
    )
    with (
        patch("app.database.AsyncSessionLocal", TestingSessionLocal),
        patch("app.services.digest.builder.build_digest", AsyncMock(return_value=fake_digest)),
        patch("app.workers.tasks.build_digest._should_deliver_email", return_value=False),
        patch("app.services.push.notify_user", AsyncMock(return_value={"sent": 1})) as notify,
    ):
        result = await _build_digest_async(user.id)
    assert result["status"] == "ok"
    assert notify.await_args.args[2] == push.digest_payload(7)
