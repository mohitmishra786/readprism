"""PKM integration endpoints — export saved items.

- GET  /integrations/obsidian       → Markdown files (downloadable)
- POST /integrations/notion         → push to a Notion database
- POST /integrations/readwise       → push to Readwise

Obsidian requires no credentials (file-based export). Notion and Readwise take
per-user tokens supplied in the request body, never stored server-side by
default.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.user import User
from app.services.integrations.export import (
    export_to_notion,
    export_to_obsidian,
    export_to_readwise,
)
from app.utils.logging import get_logger

router = APIRouter(prefix="/integrations", tags=["integrations"])
logger = get_logger(__name__)


class NotionExportRequest(BaseModel):
    notion_token: str
    database_id: str


class ReadwiseExportRequest(BaseModel):
    readwise_token: str


@router.get("/obsidian")
async def obsidian_export(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return saved items as Obsidian-flavored Markdown files.

    The frontend bundles these into a zip for download; the user drops them
    into a vault folder.
    """
    files = await export_to_obsidian(current_user.id, session)
    return {"files": files, "count": len(files)}


@router.post("/notion")
async def notion_export(
    body: NotionExportRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Push saved items to a Notion database."""
    try:
        pushed = await export_to_notion(
            current_user.id, body.notion_token, body.database_id, session
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"pushed": pushed}


@router.post("/readwise")
async def readwise_export(
    body: ReadwiseExportRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Push saved items to Readwise."""
    try:
        pushed = await export_to_readwise(current_user.id, body.readwise_token, session)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"pushed": pushed}
