"""Migrations run on startup, once, under a lock (#126)."""

from __future__ import annotations

import os
import threading
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app import migrate

SYNC_BASE = os.environ.get(
    "DATABASE_SYNC_URL", "postgresql+psycopg2://readprism:readprism@localhost:5432/readprism_test"
)


@pytest.fixture
def scratch_db():
    """A brand-new empty database; skipped if this role can't create one."""
    name = f"rp_migrate_{uuid.uuid4().hex[:8]}"
    admin_url = make_url(SYNC_BASE).set(database="postgres")
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    except Exception as e:  # pragma: no cover - environment without CREATEDB
        admin.dispose()
        pytest.skip(f"cannot create a scratch database: {e}")
    url = make_url(SYNC_BASE).set(database=name).render_as_string(hide_password=False)
    yield url
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin.dispose()


def _head(url: str) -> str:
    engine = create_engine(url)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    engine.dispose()
    return version


def _expected_head() -> str:
    from alembic.script import ScriptDirectory

    return ScriptDirectory.from_config(
        migrate._alembic_config("postgresql://unused")
    ).get_current_head()


def test_fresh_database_is_migrated_to_head_and_rerun_is_a_noop(scratch_db):
    assert migrate.run(scratch_db, attempts=1) == 0
    assert _head(scratch_db) == _expected_head()
    assert migrate.run(scratch_db, attempts=1) == 0
    assert _head(scratch_db) == _expected_head()


def test_concurrent_starts_both_succeed(scratch_db):
    results: list[int] = []

    def start() -> None:
        results.append(migrate.run(scratch_db, attempts=1))

    threads = [threading.Thread(target=start) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)
    assert results == [0, 0]
    assert _head(scratch_db) == _expected_head()


def test_auto_migrate_can_be_disabled(monkeypatch):
    monkeypatch.setenv("AUTO_MIGRATE", "false")
    assert migrate.run("postgresql+psycopg2://nobody@127.0.0.1:1/none", attempts=1) == 0


def test_unreachable_database_fails_with_nonzero_exit(monkeypatch):
    monkeypatch.delenv("AUTO_MIGRATE", raising=False)
    assert migrate.run("postgresql+psycopg2://nobody@127.0.0.1:1/none", attempts=2, delay=0) == 1
