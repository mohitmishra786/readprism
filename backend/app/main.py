from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import get_settings
from app.utils.logging import setup_logging
from app.utils.observability import init_sentry

setup_logging()
logger = logging.getLogger(__name__)
settings = get_settings()
init_sentry("api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("ReadPrism API starting up...")

    # Initialize embedding model
    from app.utils.embeddings import get_embedding_service

    try:
        emb = get_embedding_service()
        app.state.embeddings = emb
        logger.info(f"Embedding model loaded: {emb.model_name}")
    except Exception as e:
        logger.error(f"Failed to load embedding model: {e}")
        app.state.embeddings = None

    # Verify DB connection
    db_ok = False
    try:
        from sqlalchemy import text

        from app.database import engine

        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
        logger.info("Database connection: OK")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")

    # Verify Redis connection
    redis_ok = False
    try:
        from app.utils.cache import ping_redis

        redis_ok = await ping_redis()
        logger.info(f"Redis connection: {'OK' if redis_ok else 'FAILED'}")
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")

    # Settings saved on the setup screen (#220); .env values still win.
    if db_ok:
        try:
            from app.database import AsyncSessionLocal
            from app.services.instance_config import load

            async with AsyncSessionLocal() as session:
                await load(session)
        except Exception as e:
            logger.warning(f"Instance settings not loaded: {type(e).__name__}")

    app.state.db_ok = db_ok
    app.state.redis_ok = redis_ok

    yield

    logger.info("ReadPrism API shutting down...")
    from app.database import engine

    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="ReadPrism API",
        version="1.0.0",
        description="Personalized Content Intelligence Platform API",
        lifespan=lifespan,
    )

    origins = [settings.frontend_url]
    for extra in settings.cors_extra_origins.split(","):
        extra = extra.strip()
        if extra and extra not in origins:
            origins.append(extra)
    # Local dev serves the UI on 3000 (next dev) and 3001 (compose). Production
    # is exactly FRONTEND_URL plus CORS_EXTRA_ORIGINS.
    if settings.app_env == "development":
        for local in ("http://localhost:3000", "http://localhost:3001"):
            if local not in origins:
                origins.append(local)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api/v1")

    @app.get("/health")
    async def health() -> dict:
        # Redis carries rate limits, refresh tokens and webhook replay guards;
        # report a live check so an outage shows as degraded (#156).
        from app.utils.cache import ping_redis

        try:
            redis_ok = await ping_redis()
        except Exception:
            redis_ok = False
        return {
            "status": "ok" if redis_ok else "degraded",
            "db": getattr(app.state, "db_ok", False),
            "redis": redis_ok,
            "llm": settings.llm_configured,
            "llm_model": settings.llm_model_primary if settings.llm_configured else None,
            # Kept so older health checks that look at `groq` still see a bool.
            "groq": settings.llm_configured,
        }

    return app


app = create_app()
