from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import get_settings
from app.utils.logging import setup_logging

setup_logging()
logger = logging.getLogger(__name__)
settings = get_settings()


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
        from app.database import engine
        from sqlalchemy import text
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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_url, "http://localhost:3000", "http://localhost:3001"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api/v1")

    @app.get("/health")
    async def health() -> dict:
        # Check Groq connectivity
        groq_ok = bool(settings.groq_api_key)
        return {
            "status": "ok",
            "db": getattr(app.state, "db_ok", False),
            "redis": getattr(app.state, "redis_ok", False),
            "groq": groq_ok,
        }

    return app


app = create_app()
