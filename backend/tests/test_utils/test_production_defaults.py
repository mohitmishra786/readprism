"""Production-safe defaults (#106)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from app.config import Settings, validate_settings

REPO = Path(__file__).resolve().parents[3]
STRONG = "a" * 64


def _settings(monkeypatch, **env) -> Settings:
    for key in ("APP_ENV", "SECRET_KEY", "REFRESH_SECRET_KEY"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return Settings(_env_file=None)


def test_app_env_defaults_to_production(monkeypatch):
    assert _settings(monkeypatch).app_env == "production"


@pytest.mark.parametrize(
    "secret",
    [
        "",
        "change_me_to_a_long_random_string",
        "insecure-development-only-key-do-not-use-in-production",
        "short",
    ],
)
def test_production_refuses_unsafe_secret_key(monkeypatch, secret):
    s = _settings(monkeypatch, SECRET_KEY=secret)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        validate_settings(s)


def test_production_refuses_weak_refresh_key(monkeypatch):
    s = _settings(monkeypatch, SECRET_KEY=STRONG, REFRESH_SECRET_KEY="short")
    with pytest.raises(RuntimeError, match="REFRESH_SECRET_KEY"):
        validate_settings(s)


def test_production_accepts_strong_keys(monkeypatch):
    validate_settings(_settings(monkeypatch, SECRET_KEY=STRONG))
    validate_settings(_settings(monkeypatch, SECRET_KEY=STRONG, REFRESH_SECRET_KEY="b" * 64))


def test_development_allows_empty_key(monkeypatch):
    validate_settings(_settings(monkeypatch, APP_ENV="development"))


def test_env_example_is_production_shaped():
    example = (REPO / ".env.example").read_text()
    assert re.search(r"^APP_ENV=production$", example, re.M)
    assert re.search(r"^SECRET_KEY=$", example, re.M)
    assert not (REPO / "docker-compose.override.yml").exists(), "dev overrides must be opt-in"


def test_init_env_generates_secrets_and_is_idempotent(tmp_path):
    target = tmp_path / ".env"
    script = REPO / "scripts" / "init_env.sh"
    subprocess.run([str(script), str(target)], check=True, capture_output=True)
    first = target.read_text()
    values = dict(
        line.split("=", 1)
        for line in first.splitlines()
        if line and not line.startswith("#") and "=" in line
    )
    for key in ("SECRET_KEY", "REFRESH_SECRET_KEY", "METRICS_TOKEN"):
        assert re.fullmatch(r"[0-9a-f]{64}", values[key]), key
    assert values["SECRET_KEY"] != values["REFRESH_SECRET_KEY"]

    subprocess.run([str(script), str(target)], check=True, capture_output=True)
    assert target.read_text() == first
    assert oct(target.stat().st_mode & 0o777) == "0o600"
