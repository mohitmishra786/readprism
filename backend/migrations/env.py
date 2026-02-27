from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import get_settings
from app.database import Base

# Import all models so Alembic can detect them
from app.models import (  # noqa: F401
    User, Source, Creator, CreatorPlatform,
    ContentItem, UserContentInteraction,
    InterestNode, InterestEdge,
    Digest, DigestItem,
)

settings = get_settings()

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_sync_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        # Ensure pgvector extension exists
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        connection.commit()
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
