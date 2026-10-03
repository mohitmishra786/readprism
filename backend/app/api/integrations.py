"""PKM integration endpoints — export saved items.

- GET  /integrations/obsidian       → Markdown files (downloadable)
- POST /integrations/notion         → push to a Notion database
- POST /integrations/readwise       → push to Readwise

Obsidian requires no credentials (file-based export). Notion and Readwise take
per-user tokens supplied in the request body, never stored server-side by
default.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.user import User
from app.services.integrations.export import (
    export_to_logseq,
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


@router.get("/logseq")
async def logseq_export(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Saved items as Logseq pages (readprism/ folder) — EC-05."""
    files = await export_to_logseq(current_user.id, session)
    return {"files": files, "count": len(files)}


@router.get("/export-zip")
async def export_zip(
    format: str = Query("obsidian", pattern="^(obsidian|logseq)$"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """One-click folder delivery: a zip of Markdown files to drop into a
    vault (Obsidian) or pages folder (Logseq)."""
    import io
    import zipfile

    files = (
        await export_to_logseq(current_user.id, session)
        if format == "logseq"
        else await export_to_obsidian(current_user.id, session)
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in files:
            zf.writestr(file["filename"], file["content"])
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="readprism-{format}.zip"'},
    )


class WebhookExport(BaseModel):
    url: str
    format: str = Field("obsidian", pattern="^(obsidian|logseq)$")


@router.post("/export-webhook")
async def export_webhook(
    body: WebhookExport,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Push each exported Markdown file to a webhook (EC-05 folder/webhook).

    The URL is user-supplied: it goes through safe_fetch (SSRF-checked hop
    by hop), never a bare httpx call.
    """
    import json as _json

    from app.utils.ssrf import safe_fetch

    files = (
        await export_to_logseq(current_user.id, session)
        if body.format == "logseq"
        else await export_to_obsidian(current_user.id, session)
    )
    delivered = 0
    errors: list[str] = []
    for file in files:
        try:
            resp = await safe_fetch(
                body.url,
                method="POST",
                headers={"Content-Type": "application/json"},
                content=_json.dumps(file).encode(),
            )
            if resp.status_code < 300:
                delivered += 1
            else:
                errors.append(f"{file['filename']}: HTTP {resp.status_code}")
        except Exception as e:
            errors.append(f"{file['filename']}: {e}")
    return {"delivered": delivered, "total": len(files), "errors": errors[:5]}


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
