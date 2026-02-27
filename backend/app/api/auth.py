from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.user import User
from app.schemas.user import Token, TokenRefresh, UserCreate, UserLogin, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

ACCESS_TOKEN_EXPIRE_SECONDS = 86400  # 24h
ALGORITHM = "HS256"


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def _create_token(user_id: uuid.UUID, expires_in: int = ACCESS_TOKEN_EXPIRE_SECONDS) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_db),
) -> User:
    payload = _decode_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    result = await session.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
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
    token = _create_token(user.id)
    return Token(access_token=token)


@router.post("/login", response_model=Token)
async def login(body: UserLogin, session: AsyncSession = Depends(get_db)) -> Token:
    result = await session.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not _verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return Token(access_token=_create_token(user.id))


@router.post("/refresh", response_model=Token)
async def refresh(body: TokenRefresh) -> Token:
    payload = _decode_token(body.refresh_token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    return Token(access_token=_create_token(uuid.UUID(user_id)))


@router.get("/me", response_model=UserRead)
async def me(current_user: User = Depends(get_current_user)) -> UserRead:
    return UserRead.model_validate(current_user)
