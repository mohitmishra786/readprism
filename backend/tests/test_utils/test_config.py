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


def test_groq_api_key_fallback_warns_deprecation(monkeypatch):
    """#265: GROQ_API_KEY still works as a fallback but warns, removal in v0.3."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-legacy-key")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.warns(DeprecationWarning, match="removed in v0.3"):
        settings = config.get_settings()
    assert settings.llm_api_key == "gsk-legacy-key"


def test_groq_model_legacy_names_warn_deprecation(monkeypatch):
    """#265: non-retired GROQ_* model values still map through, with a warning."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("LLM_MODEL_PRIMARY", raising=False)
    monkeypatch.delenv("LLM_MODEL_FAST", raising=False)
    monkeypatch.setenv("GROQ_SUMMARIZATION_MODEL", "some-live-model")
    with pytest.warns(DeprecationWarning, match="removed in v0.3"):
        settings = config.get_settings()
    assert settings.llm_model_primary == "some-live-model"


def test_groq_alias_path_still_importable():
    """#265: tests and plugins patch groq_client.GroqSummarizer; the alias
    must keep resolving to the renamed class."""
    from app.services.summarization.groq_client import GroqSummarizer, LLMSummarizer

    assert GroqSummarizer is LLMSummarizer
