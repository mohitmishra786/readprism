"""Config safety checks (audit 06-8)."""

from __future__ import annotations

import pytest

from app import config


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


def test_default_secret_key_fails_outside_development(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", config._DEFAULT_SECRET_KEY)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        config.get_settings()


def test_default_secret_key_allowed_in_development(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("SECRET_KEY", config._DEFAULT_SECRET_KEY)
    # Should not raise.
    config.get_settings()


def test_custom_secret_key_boots_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "a-real-generated-secret")
    settings = config.get_settings()
    assert settings.secret_key == "a-real-generated-secret"
