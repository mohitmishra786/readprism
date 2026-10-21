from __future__ import annotations

import sys
from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import get_settings

settings = get_settings()


def pool_options(argv: list[str], mode: str, size: int, overflow: int) -> dict:
    """Connection pooling for this process.

    Celery runs each task in its own asyncio.run() event loop. Pooled asyncpg
    connections belong to the loop that opened them, so a shared pool in a
    worker can neither reuse nor cleanly close them: they leak until Postgres
    refuses everyone ("too many clients"; an embed worker held 49 with a pool
    of 30). Workers and beat therefore use no pool: each task opens and
    closes its own connections. The API keeps a pool.
    """
    mode = (mode or "auto").strip().lower()
    in_celery = any(Path(arg).name == "celery" for arg in argv[:1]) or (
        len(argv) > 1 and argv[1] in ("worker", "beat")
    )
    if mode == "none" or (mode == "auto" and in_celery):
        return {"poolclass": NullPool}
    return {"pool_size": size, "max_overflow": overflow}


engine = create_async_engine(
    settings.database_url,
    echo=settings.app_env == "development",
    pool_pre_ping=True,
    **pool_options(sys.argv, settings.db_pool, settings.db_pool_size, settings.db_max_overflow),
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
