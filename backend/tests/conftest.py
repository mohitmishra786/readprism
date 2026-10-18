from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator

# The app defaults to production (#106). The suite runs in development mode
# unless TEST_APP_ENV says otherwise; tests that check production behavior set
# it per test. Must happen before `app` is imported (settings load on import).
os.environ["APP_ENV"] = os.environ.get("TEST_APP_ENV", "development")
# Most tests register several users; registration rules are tested explicitly.
# Override an empty value too: CI's .env (from .env.example) sets
# REGISTRATION_MODE= and an empty value means "closed" on selfhost.
if not os.environ.get("REGISTRATION_MODE"):
    os.environ["REGISTRATION_MODE"] = "open"

# Host-side Redis defaults: outside Docker, `redis` host is not resolvable.
# Fall back to localhost:6379 so tests needing Redis (rate limits, magic links,
# background queues) pass out of the box when Redis runs on the host or via
# docker-compose.test.yml. Must happen before `app` is imported.
if "REDIS_URL" not in os.environ:
    os.environ["REDIS_URL"] = "redis://127.0.0.1:6379/0"
if "CELERY_BROKER_URL" not in os.environ:
    os.environ["CELERY_BROKER_URL"] = "redis://127.0.0.1:6379/0"
if "CELERY_RESULT_BACKEND" not in os.environ:
    os.environ["CELERY_RESULT_BACKEND"] = "redis://127.0.0.1:6379/0"

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app import (
    models,  # register all models on Base.metadata so create_all/drop_all see the full schema
)
from app.database import Base, get_db
from app.main import app

# Read the test DB URL from the environment so the suite works both on the host
# (localhost:5432) and inside the backend container (db:5432).
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://readprism:readprism@localhost:5432/readprism_test",
)

# Dedicated test engine. NullPool is the key to isolation: it opens a fresh
# connection per session and never holds one across tests, so commits inside one
# test can't leak a poisoned connection to the next.
from sqlalchemy.pool import NullPool

engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
TestingSessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)


@pytest.fixture(autouse=True)
def _cleanup_redis_client():
    from app.utils import cache

    yield
    cache._redis_client = None


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create the schema, yield a session, then drop everything and dispose."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestingSessionLocal() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Test client; each endpoint request gets its own session from the test engine."""

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with TestingSessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _disable_rate_limit(monkeypatch):
    """Disable auth rate limiting by default: the whole suite shares one client
    IP, so the fixed-window counters would otherwise accumulate across tests and
    spuriously 429. The dedicated rate-limit test re-enables it explicitly.
    """
    from app.utils import cache, ratelimit

    cache._redis_client = None
    monkeypatch.setattr(ratelimit.settings, "rate_limit_enabled", False)
    yield
    cache._redis_client = None


@pytest.fixture
def test_user_data():
    return {
        "email": f"test_{uuid.uuid4().hex[:8]}@example.com",
        "password": "TestPass123!",
        "display_name": "Test User",
    }
