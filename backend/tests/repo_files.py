"""Locate repository-level files (compose, deploy/, scripts/) from the tests.

In CI the backend suite runs inside the container, where only backend/ is
mounted; tests that check deployment files skip there and run in the
host-side "Config checks" job instead.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def repo_root() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        if (parent / "docker-compose.yml").exists() and (parent / "backend").is_dir():
            return parent
    return None


def require_repo_root() -> Path:
    root = repo_root()
    if root is None:
        pytest.skip("repository files not available (backend-only mount)", allow_module_level=True)
    return root
