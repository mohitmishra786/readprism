from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.user import User
from app.services.account.gdpr import delete_user_account, export_user_data
from app.utils.logging import get_logger

router = APIRouter(prefix="/account", tags=["account"])
logger = get_logger(__name__)


@router.get("/export")
async def export_account(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JSONResponse:
    """Download a portable JSON copy of all your personal data (GDPR Art. 20)."""
    bundle = await export_user_data(session, current_user)
    return JSONResponse(
        content=bundle,
        headers={"Content-Disposition": 'attachment; filename="readprism-export.json"'},
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_account(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Permanently delete your account and all associated data (GDPR Art. 17).

    This is irreversible. Teams you created are deleted along with your account.
    """
    await delete_user_account(session, current_user.id)
