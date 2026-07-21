from __future__ import annotations

from functools import lru_cache

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

    # Application
    app_env: str = "development"
    secret_key: str = "change_me_to_a_long_random_string"
    # Optional distinct signing key for refresh tokens (defense in depth). Falls
    # back to secret_key when empty.
    refresh_secret_key: str = ""
    # Short-lived access tokens + long-lived, revocable refresh tokens.
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30
    frontend_url: str = "http://localhost:3000"

    # Database
    database_url: str = "postgresql+asyncpg://readprism:readprism@db:5432/readprism"
    database_sync_url: str = "postgresql://readprism:readprism@db:5432/readprism"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # LLM — Primary: Groq
    groq_api_key: str = ""
    groq_summarization_model: str = "llama-3.3-70b-versatile"
    groq_fast_model: str = "llama-3.1-8b-instant"

    # LLM — Fallback: OpenAI (disabled by default)
    openai_fallback_enabled: bool = False
    openai_api_key: str = ""

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

    # Content retention: after this many days, the stored full article text is
    # pruned to a short excerpt (keeping summary + link). Limits how long we hold
    # full third-party copies — a copyright-exposure control (audit 08-3).
    # Set 0 to disable pruning (keep full text indefinitely).
    content_full_text_retention_days: int = 90
    content_excerpt_chars: int = 500

    # Scraping
    browserless_url: str = "http://browserless:3000"
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

    # Feature flags
    cold_start_collaborative_enabled: bool = True
    # Collaborative warmup is mathematically inert below a critical mass of active
    # users with warm interest vectors; gate it off until then rather than
    # pretending it contributes at launch (audit 05-6).
    collaborative_warmup_min_users: int = 1000
    serendipity_default_percentage: int = 15
    digest_default_items: int = 12

    @property
    def llm_configured(self) -> bool:
        """True if at least one LLM backend is configured.

        When False, the summarizer short-circuits (no retries) and onboarding
        falls back to keyword topic extraction, so the app still works — just
        without AI summaries. The health endpoint reports this explicitly.
        """
        return bool(self.groq_api_key) or (
            self.openai_fallback_enabled and bool(self.openai_api_key)
        )


_DEFAULT_SECRET_KEY = "change_me_to_a_long_random_string"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()

    # Refuse to boot outside development with the placeholder signing key — a
    # default SECRET_KEY means every JWT is forgeable (audit 06-8).
    if s.app_env != "development" and s.secret_key == _DEFAULT_SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY is still the insecure default in a non-development "
            f"environment (APP_ENV={s.app_env!r}). Generate one with "
            '`python -c "import secrets; print(secrets.token_hex(32))"` and set '
            "it in the environment before deploying."
        )

    if not s.llm_configured:
        # Loud, actionable warning so the operator knows summaries are disabled.
        import warnings

        warnings.warn(
            "GROQ_API_KEY is not set. Summaries, topic extraction, and "
            "cross-source synthesis will be skipped. Get a free key at "
            "https://console.groq.com/ and set it in .env.",
            stacklevel=2,
        )
    return s
