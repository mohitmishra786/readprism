from __future__ import annotations

from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.content import router as content_router
from app.api.creators import router as creators_router
from app.api.digest import router as digest_router
from app.api.feedback import router as feedback_router
from app.api.newsletter import router as newsletter_router
from app.api.onboarding import router as onboarding_router
from app.api.preferences import router as preferences_router
from app.api.search import router as search_router
from app.api.sources import router as sources_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(onboarding_router)
api_router.include_router(sources_router)
api_router.include_router(creators_router)
api_router.include_router(content_router)
api_router.include_router(digest_router)
api_router.include_router(feedback_router)
api_router.include_router(preferences_router)
api_router.include_router(search_router)
api_router.include_router(newsletter_router)
