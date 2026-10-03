"""API token management (EC-03)."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.api_token import ApiToken, new_api_token
from app.models.user import User

router = APIRouter(prefix="/tokens", tags=["tokens"])

VALID_SCOPES = {"read", "write"}


class TokenCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    scopes: list[str] = Field(default_factory=lambda: ["read"])


class TokenRead(BaseModel):
    id: uuid.UUID
    name: str
    prefix: str
    scopes: list[str]
    created_at: datetime
    last_used_at: datetime | None
    revoked: bool
    use_count: int

    model_config = {"from_attributes": True}


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_token(
    body: TokenCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    scopes = sorted({s for s in body.scopes if s in VALID_SCOPES}) or ["read"]
    plaintext, token_hash, prefix = new_api_token()
    row = ApiToken(
        user_id=current_user.id,
        name=body.name.strip() or "token",
        token_hash=token_hash,
        prefix=prefix,
        scopes=scopes,
    )
    session.add(row)
    await session.flush()
    # The plaintext is returned exactly once; only the hash is stored.
    return {"id": str(row.id), "name": row.name, "token": plaintext, "scopes": scopes}


@router.get("", response_model=list[TokenRead])
async def list_tokens(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[TokenRead]:
    result = await session.execute(
        select(ApiToken)
        .where(ApiToken.user_id == current_user.id)
        .order_by(ApiToken.created_at.desc())
    )
    return [TokenRead.model_validate(row) for row in result.scalars().all()]


@router.delete("/{token_id}", response_model=dict)
async def revoke_token(
    token_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    result = await session.execute(
        select(ApiToken).where(ApiToken.id == token_id, ApiToken.user_id == current_user.id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")
    row.revoked = True
    await session.flush()
    return {"status": "revoked", "id": str(token_id)}
