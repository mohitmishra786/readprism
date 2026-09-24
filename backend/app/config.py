from __future__ import annotations

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Observability — error tracking. Opt-in: no DSN => Sentry stays disabled.
    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.0
    # Aggregate/operator metrics (cohort retention, North Star, scraper health)
    # are gated behind this token via the X-Metrics-Token header. Required in
    # non-development environments; open in development for convenience.
    metrics_token: str = ""

    # Application
    app_env: str = "development"
    secret_key: str = "change_me_to_a_long_random_string"
    # Optional distinct signing key for refresh tokens (defense in depth). Falls
    # back to secret_key when empty.
    refresh_secret_key: str = ""
    # Short-lived access tokens + long-lived, revocable refresh tokens.
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30
    # Passwordless magic-link sign-in (audit 10-8): single-use, short-lived.
    magic_link_expire_minutes: int = 20
    frontend_url: str = "http://localhost:3000"

    # Database
    database_url: str = "postgresql+asyncpg://readprism:readprism@db:5432/readprism"
    database_sync_url: str = "postgresql://readprism:readprism@db:5432/readprism"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # LLM — OpenAI-compatible endpoint. Groq is the default base URL.
    # Model ids are configuration, not code. GROQ_* names still work.
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_api_key: str = ""
    llm_model_primary: str = "openai/gpt-oss-120b"
    llm_model_fast: str = "openai/gpt-oss-20b"
    llm_tpm_limit: int = 6000
    llm_rpm_limit: int = 30
    llm_timeout_seconds: float = 30.0
    # Legacy aliases. A retired model id is rewritten in `_normalize_llm`.
    groq_api_key: str = ""
    groq_summarization_model: str = ""
    groq_fast_model: str = ""

    # Optional second provider. Used only when all three are set.
    openai_fallback_enabled: bool = False
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = ""
    # Comma-separated origins allowed in addition to FRONTEND_URL.
    cors_extra_origins: str = ""
    rate_limit_feedback_per_minute: int = 60
    # Feed / OPML body cap and outline cap (XML bombs and huge imports).
    xml_max_bytes: int = 2_000_000
    opml_max_outlines: int = 5000

    # Embeddings (local sentence-transformers)
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_device: str = "cpu"

    # Email delivery — Zoho SMTP
    zoho_smtp_host: str = "smtppro.zoho.in"
    zoho_smtp_port: int = 587
    zoho_email: str = "admin@mohitmishra7.com"
    zoho_password: str = ""
    from_email: str = "admin@mohitmishra7.com"
    # Externally-reachable base URL of this API — used to build one-click
    # unsubscribe links in digest emails (must be publicly routable in prod).
    public_api_url: str = "http://localhost:8000"
    # Physical mailing address shown in the email footer (CAN-SPAM). Optional
    # for self-host; set it for any real bulk sending.
    email_physical_address: str = ""

    # Newsletter ingestion
    newsletter_inbox_domain: str = "inbox.readprism.app"
    mailgun_api_key: str = ""
    mailgun_domain: str = ""
    # Dedicated Mailgun *Webhook Signing Key* (Settings → API Security), NOT the
    # API key. Used to HMAC-verify inbound-route posts to /newsletter/inbound.
    # When empty in a non-development environment, the webhook is fail-closed
    # (rejects everything) so an unauthenticated open door can never ship.
    mailgun_webhook_signing_key: str = ""
    # Reject webhook posts whose signed timestamp is older than this (replay guard).
    newsletter_webhook_max_age_seconds: int = 900  # 15 minutes

    # Win-back: email users who haven't opened a digest in this many days (once
    # per re-engagement cooldown) to bring lapsed readers back (audit 10-5).
    reengagement_inactivity_days: int = 14
    reengagement_cooldown_days: int = 30

    # Content retention: after this many days, the stored full article text is
    # pruned to a short excerpt (keeping summary + link). Limits how long we hold
    # full third-party copies — a copyright-exposure control (audit 08-3).
    # Set 0 to disable pruning (keep full text indefinitely).
    content_full_text_retention_days: int = 90
    content_excerpt_chars: int = 500

    # Scraping
    browserless_url: str = "http://browserless:3000"
    # Optional RSSHub instance. Empty disables the discovery route (IN-06).
    rsshub_base_url: str = ""
    scraper_max_concurrency: int = 5
    # When robots.txt can't be fetched (network error / 5xx), fail closed (deny)
    # by default — an honest good-faith posture (audit 08-6). A clean 404/410
    # (no robots.txt served) still means "allowed" per convention. Set True to
    # restore the permissive legacy behaviour.
    robots_fail_open: bool = False
    robots_cache_ttl_seconds: int = 86400  # cache robots.txt per host for 24h
    # Scraping posture (audit 08-2). Honest by default:
    #  - identify as the ReadPrism bot (no browser-impersonation User-Agents), and
    #  - on an explicit block (403/429/503), back off instead of escalating to a
    #    headless browser to circumvent it.
    # The 2026 §1201 anti-circumvention landscape targets bypassing anti-bot
    # measures; operators who accept that risk can set these False.
    scraper_identify_as_bot: bool = True
    scraper_respect_blocks: bool = True
    # SSRF protection: resolve and block private/loopback/link-local/reserved IPs
    # before any server-side URL fetch (scraping, feed autodiscovery, robots.txt).
    # Keep True for any hosted/multi-tenant deployment. Self-hosters who need to
    # ingest feeds from private/LAN hosts (e.g. a homelab service on 192.168.x)
    # may set this False, accepting the SSRF trade-off on a single-tenant box.
    ssrf_protection_enabled: bool = True

    # Celery
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"

    # Meilisearch
    meilisearch_url: str = "http://meilisearch:7700"
    meilisearch_master_key: str = "readprism_search_key"

    # Rate limiting (Redis-backed, fixed window). Guards auth endpoints against
    # credential stuffing and registration spam.
    rate_limit_enabled: bool = True
    rate_limit_login_per_minute: int = 10
    rate_limit_register_per_minute: int = 5

    # Ranking-signal tunables (audit 05-8). Previously hard-coded magic constants;
    # exposed so they can be tuned per-deployment (and eventually learned) without
    # a code change.
    novelty_target: float = 0.35  # novelty level the novelty signal peaks at
    temporal_blend_long: float = 0.50  # long-term interest weight
    temporal_blend_medium: float = 0.35  # medium-term focus weight
    temporal_blend_short: float = 0.15  # session/short-term weight

    # Tier entitlements (audit 13-1/13-5). Free-tier quantity limits; 0 = unlimited.
    # These are config-driven scaffolding — the final Free/Pro structure is a
    # business decision (see IMPLEMENTATION_LOG "Needs Human Decision"). Pro is
    # unlimited by default. Only enforced when `tier == "free"`.
    free_max_sources: int = 30
    free_max_creators: int = 5

    # Feature flags
    cold_start_collaborative_enabled: bool = True
    # Collaborative warmup is mathematically inert below a critical mass of active
    # users with warm interest vectors; gate it off until then rather than
    # pretending it contributes at launch (audit 05-6).
    collaborative_warmup_min_users: int = 1000
    serendipity_default_percentage: int = 15
    digest_default_items: int = 12

    @model_validator(mode="after")
    def _normalize_llm(self) -> Settings:
        """Honor legacy GROQ_* env vars and refuse retired Groq model ids."""
        if not self.llm_api_key and self.groq_api_key:
            self.llm_api_key = self.groq_api_key
        self.llm_model_primary = _resolve_model(
            configured=self.llm_model_primary,
            legacy=self.groq_summarization_model,
            default=_DEFAULT_LLM_PRIMARY,
            legacy_name="GROQ_SUMMARIZATION_MODEL",
        )
        self.llm_model_fast = _resolve_model(
            configured=self.llm_model_fast,
            legacy=self.groq_fast_model,
            default=_DEFAULT_LLM_FAST,
            legacy_name="GROQ_FAST_MODEL",
        )
        return self

    @property
    def llm_configured(self) -> bool:
        """True if at least one LLM backend is configured.

        When False, summaries are extractive and onboarding falls back to
        keyword topic extraction. The health endpoint reports this explicitly.
        """
        return bool(self.llm_api_key) or (
            self.openai_fallback_enabled and bool(self.openai_api_key) and bool(self.openai_model)
        )


_DEFAULT_SECRET_KEY = "change_me_to_a_long_random_string"
_MIN_SECRET_LEN = 32
_DEFAULT_LLM_PRIMARY = "openai/gpt-oss-120b"
_DEFAULT_LLM_FAST = "openai/gpt-oss-20b"
# Recognized only so a leftover env var cannot keep calling a dead model.
_RETIRED_LLM_MODELS = {
    "llama-3.3-70b-versatile": _DEFAULT_LLM_PRIMARY,
    "llama-3.1-8b-instant": _DEFAULT_LLM_FAST,
}


def _resolve_model(*, configured: str, legacy: str, default: str, legacy_name: str) -> str:
    """Prefer an explicit LLM_MODEL_* value; otherwise map a legacy GROQ_* value."""
    import warnings

    if configured and configured != default:
        if configured in _RETIRED_LLM_MODELS:
            replacement = _RETIRED_LLM_MODELS[configured]
            warnings.warn(
                f"LLM model {configured!r} was retired. Using {replacement!r}. "
                "Set LLM_MODEL_PRIMARY / LLM_MODEL_FAST to a live model id.",
                stacklevel=2,
            )
            return replacement
        return configured
    if not legacy:
        return default
    if legacy in _RETIRED_LLM_MODELS:
        replacement = _RETIRED_LLM_MODELS[legacy]
        warnings.warn(
            f"{legacy_name}={legacy!r} was retired by the provider on 2026-08-16. "
            f"Using {replacement!r}. Set LLM_MODEL_PRIMARY and LLM_MODEL_FAST "
            "and remove the GROQ_* model variables.",
            stacklevel=2,
        )
        return replacement
    return legacy


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()

    # Refuse to boot outside development with the placeholder signing key — a
    # default SECRET_KEY means every JWT is forgeable (audit 06-8).
    if s.app_env != "development" and (
        s.secret_key == _DEFAULT_SECRET_KEY or len(s.secret_key) < _MIN_SECRET_LEN
    ):
        raise RuntimeError(
            "SECRET_KEY is missing, still the insecure default, or shorter than "
            f"{_MIN_SECRET_LEN} characters in a non-development environment "
            f"(APP_ENV={s.app_env!r}). Generate one with "
            '`python -c "import secrets; print(secrets.token_hex(32))"` and set '
            "it in the environment before deploying."
        )

    if not s.llm_configured:
        import warnings

        warnings.warn(
            "LLM_API_KEY is not set (GROQ_API_KEY is also accepted). "
            "Summaries will use the extractive fallback and topic extraction "
            "will use keywords. The digest still builds.",
            stacklevel=2,
        )
    return s
