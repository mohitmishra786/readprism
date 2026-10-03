"""API tokens (EC-03): scoped, hashed-at-rest access tokens for /api/v1.

Format: rp_<32 url-safe chars>. Only the SHA-256 hash is stored; the
plaintext is shown exactly once at creation. Scopes: "read" (default) and
"write" (mutating endpoints).
"""

from __future__ import annotations

import hashlib
import secrets
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def new_api_token() -> tuple[str, str, str]:
    """Return (plaintext, sha256_hash, display_prefix)."""
    plaintext = f"rp_{secrets.token_urlsafe(32)}"
    return plaintext, hash_api_token(plaintext), plaintext[:12]


def hash_api_token(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()


class ApiToken(Base):
    __tablename__ = "api_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    scopes: Mapped[list] = mapped_column(JSONB, default=lambda: ["read"], server_default='["read"]')
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_used_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    # int, not bool: quick "uses this month" counter for the token list UI.
    use_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
