"""#199: make eval / retrieval-eval targets; eval scripts are read-only by default."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests.repo_files import require_repo_root


def test_ranking_eval_is_readonly_by_default_and_writes_with_flag(monkeypatch, tmp_path):
    """ "Running without --write writes nothing; --write PATH persists the report."""
    import asyncio

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    try:
        import ranking_eval
    finally:
        sys.path.pop(0)

    # The script opens its own sessions: point it at the test database.
    from tests.conftest import TestingSessionLocal, engine

    monkeypatch.setattr("app.database.AsyncSessionLocal", TestingSessionLocal)
    target = tmp_path / "ranking-observed.md"

    from app import models
    from app.database import Base

    async def _create() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def _drop() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    asyncio.run(_create())
    try:
        monkeypatch.setattr(sys, "argv", ["ranking_eval.py", "--days", "30"])
        ranking_eval.main()  # no --write: nothing persisted (prints only)
        assert not target.exists()

        monkeypatch.setattr(
            sys, "argv", ["ranking_eval.py", "--days", "30", "--write", str(target)]
        )
        ranking_eval.main()
    finally:
        asyncio.run(_drop())
    # --write persisted the report exactly as printed.
    assert target.exists() and target.read_text(encoding="utf-8").strip()


def test_makefile_has_readonly_eval_targets():
    """The documented `make eval` / `make retrieval-eval` targets exist and do
    not pass --write (default runs must leave git status clean)."""
    makefile = require_repo_root() / "Makefile"
    text = makefile.read_text(encoding="utf-8")
    assert "\neval:\n" in text
    assert "\nretrieval-eval:\n" in text
    eval_recipe = text.split("eval:\n", 1)[1].split("\n", 2)[1]
    assert "--write" not in eval_recipe
