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
    monkeypatch.setenv("SECRET_KEY", "prod-secret-key-must-be-at-least-32")
    settings = config.get_settings()
    assert settings.secret_key == "prod-secret-key-must-be-at-least-32"


def test_short_secret_key_fails_outside_development(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "too-short")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        config.get_settings()


def test_retired_groq_model_is_rewritten(monkeypatch):
    monkeypatch.setenv("GROQ_SUMMARIZATION_MODEL", "llama-3.3-70b-versatile")
    monkeypatch.setenv("GROQ_FAST_MODEL", "llama-3.1-8b-instant")
    settings = config.get_settings()
    assert settings.llm_model_primary == "openai/gpt-oss-120b"
    assert settings.llm_model_fast == "openai/gpt-oss-20b"
