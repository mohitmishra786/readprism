"""Apply database migrations on startup (#126).

    python -m app.migrate

Runs `alembic upgrade head` under a Postgres advisory lock, so several
containers starting at once migrate exactly once (the others wait, then find
nothing to do). Set AUTO_MIGRATE=false to skip, e.g. when an operator runs
migrations as a separate release step.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from sqlalchemy import create_engine, text

# Arbitrary, fixed key for pg_advisory_lock: "readprism migrations".
MIGRATION_LOCK_ID = 7_302_410_126
BACKEND_DIR = Path(__file__).resolve().parents[1]


def _enabled() -> bool:
    return os.environ.get("AUTO_MIGRATE", "true").strip().lower() not in ("0", "false", "no", "off")


def _alembic_config(url: str):
    from alembic.config import Config

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.attributes["sqlalchemy_url"] = url
    return cfg


def run(url: str | None = None, *, attempts: int = 10, delay: float = 2.0) -> int:
    """Upgrade to head; returns a process exit code."""
    if not _enabled():
        print("migrate: AUTO_MIGRATE is off; skipping", flush=True)
        return 0
    from alembic import command

    if url is None:
        from app.config import get_settings

        url = get_settings().database_sync_url
    engine = create_engine(url, pool_pre_ping=True)
    for attempt in range(1, attempts + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT pg_advisory_lock(:id)"), {"id": MIGRATION_LOCK_ID})
                try:
                    print("migrate: upgrading to head", flush=True)
                    command.upgrade(_alembic_config(url), "head")
                finally:
                    conn.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": MIGRATION_LOCK_ID})
            print("migrate: database is at head", flush=True)
            return 0
        except Exception as e:  # database not reachable yet, or a failed migration
            if attempt == attempts:
                print(
                    f"migrate: failed after {attempts} attempts: {e}", file=sys.stderr, flush=True
                )
                return 1
            print(f"migrate: attempt {attempt} failed ({e}); retrying", file=sys.stderr, flush=True)
            time.sleep(delay)
        finally:
            engine.dispose()
    return 1


if __name__ == "__main__":
    sys.exit(run())
