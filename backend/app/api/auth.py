from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.user import User
from app.schemas.user import Token, TokenRefresh, UserCreate, UserLogin, UserRead
from app.utils.cache import cache_delete, cache_get, cache_set
from app.utils.ratelimit import RateLimiter

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

ALGORITHM = "HS256"


def _access_secret() -> str:
    return settings.secret_key


def _refresh_secret() -> str:
    return settings.refresh_secret_key or settings.secret_key


def _refresh_allowlist_key(jti: str) -> str:
    return f"refresh:{jti}"


login_rate_limit = RateLimiter(
    max_requests=settings.rate_limit_login_per_minute, window_seconds=60, scope="login"
)
register_rate_limit = RateLimiter(
    max_requests=settings.rate_limit_register_per_minute, window_seconds=60, scope="register"
)

# Precomputed bcrypt hash of a random string, used to spend the same time on a
# password check whether or not the account exists — closing the login timing
# oracle that would otherwise reveal which emails are registered (audit 06-4).
_DUMMY_HASH = bcrypt.hashpw(b"timing-oracle-mitigation", bcrypt.gensalt()).decode()


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def _create_access_token(user_id: uuid.UUID) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, _access_secret(), algorithm=ALGORITHM)


async def _create_refresh_token(user_id: uuid.UUID) -> str:
    """Mint a refresh token and record its jti in the Redis allowlist so it can
    be rotated/revoked. A refresh token is only valid while its jti is present."""
    now = datetime.now(UTC)
    jti = uuid.uuid4().hex
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "jti": jti,
        "iat": now,
        "exp": now + timedelta(days=settings.refresh_token_expire_days),
    }
    token = jwt.encode(payload, _refresh_secret(), algorithm=ALGORITHM)
    await cache_set(
        _refresh_allowlist_key(jti),
        str(user_id),
        ttl_seconds=settings.refresh_token_expire_days * 86400,
    )
    return token


def _decode_token(token: str, *, secret: str) -> dict:
    try:
        return jwt.decode(token, secret, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_db),
) -> User:
    payload = _decode_token(token, secret=_access_secret())
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload"
        )

    result = await session.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


async def _issue_tokens(user_id: uuid.UUID) -> Token:
    return Token(
        access_token=_create_access_token(user_id),
        refresh_token=await _create_refresh_token(user_id),
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post(
    "/register",
    response_model=Token,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(register_rate_limit)],
)
async def register(body: UserCreate, session: AsyncSession = Depends(get_db)) -> Token:
    existing = await session.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=body.email,
        hashed_password=_hash_password(body.password),
        display_name=body.display_name,
    )
    session.add(user)
    await session.flush()
    return await _issue_tokens(user.id)


@router.post("/login", response_model=Token, dependencies=[Depends(login_rate_limit)])
async def login(body: UserLogin, session: AsyncSession = Depends(get_db)) -> Token:
    result = await session.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    # Always run a bcrypt verification (against a dummy hash when the user is
    # absent) so response time doesn't reveal whether the email exists.
    password_ok = _verify_password(body.password, user.hashed_password if user else _DUMMY_HASH)
    if not user or not password_ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return await _issue_tokens(user.id)


@router.post("/refresh", response_model=Token)
async def refresh(body: TokenRefresh) -> Token:
    """Rotate a refresh token: verify it, revoke it (single-use), and issue a
    fresh access+refresh pair. A revoked/rotated/unknown jti is rejected, so a
    leaked refresh token can be killed via logout and can't be replayed."""
    payload = _decode_token(body.refresh_token, secret=_refresh_secret())
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )
    user_id = payload.get("sub")
    jti = payload.get("jti")
    if not user_id or not jti:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )
    # The jti must still be in the allowlist (not rotated out or revoked).
    stored = await cache_get(_refresh_allowlist_key(jti))
    if stored != str(user_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked or expired"
        )
    await cache_delete(_refresh_allowlist_key(jti))  # rotate: single-use
    return await _issue_tokens(uuid.UUID(user_id))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def logout(body: TokenRefresh) -> None:
    """Revoke a refresh token server-side so it can no longer be rotated."""
    try:
        payload = jwt.decode(
            body.refresh_token,
            _refresh_secret(),
            algorithms=[ALGORITHM],
            options={"verify_exp": False},
        )
    except jwt.InvalidTokenError:
        return  # nothing to revoke on a malformed token
    jti = payload.get("jti")
    if jti:
        await cache_delete(_refresh_allowlist_key(jti))


@router.get("/me", response_model=UserRead)
async def me(current_user: User = Depends(get_current_user)) -> UserRead:
    return UserRead.model_validate(current_user)
