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

    This is irreversible. On hosted, a running subscription is cancelled
    first; if that fails the data is still deleted and the operator is told
    (#221). The user gets a confirmation email.
    """
    from app.services import billing
    from app.services.email_verification import may_email

    email = current_user.email if may_email(current_user) else None
    cancel = await billing.cancel_for_deletion(session, current_user)
    await delete_user_account(session, current_user.id)
    await session.commit()
    if email:
        await _send_erasure_confirmation(email, subscription_cancelled=cancel)


async def _send_erasure_confirmation(email: str, *, subscription_cancelled: str) -> None:
    from app.utils.email import send_email

    lines = [
        "Your ReadPrism account and everything in it (sources, saved articles, ratings, "
        "digests) have been deleted. This can't be undone.",
    ]
    if subscription_cancelled == "cancelled":
        lines.append("Your subscription has been cancelled, so you won't be charged again.")
    elif subscription_cancelled == "failed":
        lines.append(
            "We couldn't cancel your subscription automatically. We've been notified and will "
            "cancel it by hand. If you're charged again, reply to this email."
        )
    lines.append("You're receiving this because you asked for the deletion.")
    await send_email(
        to=email,
        subject="Your ReadPrism account has been deleted",
        html_body="".join(f"<p>{line}</p>" for line in lines),
        text_body="\n\n".join(lines),
    )
