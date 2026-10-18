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

    # Application. Production is the default (#106): development mode relaxes
    # webhook authentication, opens operator metrics and echoes SQL, so it must
    # be chosen explicitly (APP_ENV=development, set by docker-compose.dev.yml).
    app_env: str = "production"
    # No usable default: generate one with scripts/init_env.sh. Outside
    # development the app refuses to start with an empty, short or published key.
    secret_key: str = ""
    # Optional distinct signing key for refresh tokens (defense in depth). Falls
    # back to secret_key when empty.
    refresh_secret_key: str = ""
    # Short-lived access tokens + long-lived, revocable refresh tokens.
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30
    # Self-host only (#164): let the Miniflux/FreshRSS sidecar import reach the
    # configured server over plain http on a private address (typical homelab).
    # Never honored when DEPLOYMENT_MODE=hosted.
    sidecar_allow_private_http: bool = False
    # Who may register (#153): closed | invite | open. Empty = closed on
    # selfhost (only the first account), open on hosted.
    registration_mode: str = ""
    registration_invite_codes: str = ""
    # Email verification before any non-verification email or inbound
    # newsletter (#175): "auto" = required on hosted, off on selfhost.
    email_verification: str = "auto"
    email_verification_expire_hours: int = 48
    # Signups per email domain per hour (hosted, #175). Large mail providers
    # get `signup_per_domain_per_hour * 20`.
    signup_per_domain_per_hour: int = 10
    # Session cookies (#103). Leave empty for a host-only cookie; set e.g.
    # ".example.com" when the API and web app are on different subdomains.
    cookie_domain: str = ""
    # "auto" (default): Secure flag follows the request scheme (honors
    # X-Forwarded-Proto from a TLS proxy). "true"/"false" force it.
    cookie_secure: str = "auto"
    # Passwordless magic-link sign-in (audit 10-8): single-use, short-lived.
    magic_link_expire_minutes: int = 20
    frontend_url: str = "http://localhost:3000"

    # Database
    database_url: str = "postgresql+asyncpg://readprism:readprism@db:5432/readprism"
    database_sync_url: str = "postgresql+psycopg2://readprism:readprism@db:5432/readprism"

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
    # "lazy" (default): extractive at ingest, LLM only for items placed in a
    # digest or opened in the reader (#147). "all": LLM for every item.
    llm_summarize: str = "lazy"
    # Max LLM summaries requested per digest build.
    digest_llm_summary_limit: int = 20
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
    # Leave false until the golden retrieval ADR says nomic beat MiniLM.
    embedding_cutover_enabled: bool = False
    ranking_exploration_enabled: bool = False
    # Team-draft interleave PRS with newest-first in every digest and log teams,
    # to measure the PRS win rate (#130). For the beta; off by default.
    ranking_interleaving: bool = False
    ranker_version: str = "2"

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
    content_per_source_cap: int = 500
    source_backfill_limit: int = 20
    digest_per_source_cap: int = 3
    # A digest with fewer rankable items than this is "not worth an email":
    # still built for in-app, but delivery is skipped (UX-03).
    digest_min_items: int = 3
    # Comma-separated hosts the scraper will not touch, even if robots allows them.
    scraper_deny_domains: str = ""
    postmark_webhook_secret: str = ""
    resend_webhook_secret: str = ""
    cloudflare_email_webhook_secret: str = ""
    newsletter_domain: str = "newsletters.readprism.local"

    # Scraping
    browserless_url: str = "http://browserless:3000"
    # Rendered extraction runs arbitrary third-party pages in Chrome. On the
    # hosted service it stays off unless the renderer sits behind the egress
    # proxy (docker-compose `full` profile) and this is set (#127).
    browserless_hosted_allowed: bool = False
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

    # Deployment mode (#109): "selfhost" (default) never applies plan limits;
    # "hosted" applies the free-tier limits below to tier == "free" users.
    deployment_mode: str = "selfhost"
    # Hosted free-tier quantity limits; 0 = unlimited. Final plan structure is
    # a business decision (see #138). Ignored in selfhost mode.
    free_max_sources: int = 30
    free_max_creators: int = 5
    hosted_free_digest_regen_minutes: int = 60
    # Abuse controls on hosted (#169). 0 disables a limit.
    hosted_fetch_budget_per_hour: int = 300  # feed polls + on-demand fetches per account
    hosted_host_polls_per_hour: int = 120  # polls of one host across all accounts
    hosted_max_sources_per_host: int = 10  # one account's subscriptions on one host
    hosted_inbound_per_day: int = 100  # newsletter emails per account
    hosted_inbound_mb_per_day: int = 25
    # Any instance: a single inbound newsletter larger than this is dropped.
    inbound_max_message_bytes: int = 2_000_000
    # Self-host and paid plans: only guards against double-clicking "generate".
    manual_digest_guard_seconds: int = 60

    # Feature flags
    cold_start_collaborative_enabled: bool = True
    # Collaborative warmup is mathematically inert below a critical mass of active
    # users with warm interest vectors; gate it off until then rather than
    # pretending it contributes at launch (audit 05-6).
    collaborative_warmup_min_users: int = 1000
    serendipity_default_percentage: int = 15
    digest_default_items: int = 12

    @model_validator(mode="after")
    def _check_deployment_mode(self) -> Settings:
        mode = self.deployment_mode.strip().lower()
        if mode not in ("selfhost", "hosted"):
            raise ValueError(f"DEPLOYMENT_MODE must be 'selfhost' or 'hosted', got {mode!r}")
        self.deployment_mode = mode
        return self

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
# Used only when APP_ENV=development and SECRET_KEY is empty. Public by design.
_DEV_ONLY_SECRET_KEY = "insecure-development-only-key-do-not-use-in-production"
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


def validate_settings(s: Settings) -> None:
    """Refuse to boot outside development with an unsafe signing key.

    A known SECRET_KEY makes every JWT forgeable, and the user id in the token
    is also in every digest email link (audit 06-8, #106). The published
    placeholder is rejected even if an old .env still carries it.
    """
    if s.app_env == "development":
        if not s.secret_key:
            import warnings

            warnings.warn(
                "SECRET_KEY is empty; using an insecure development-only key. "
                "Never expose a development instance.",
                stacklevel=2,
            )
            s.secret_key = _DEV_ONLY_SECRET_KEY
        return
    for name, value in (("SECRET_KEY", s.secret_key), ("REFRESH_SECRET_KEY", s.refresh_secret_key)):
        if name == "REFRESH_SECRET_KEY" and not value:
            continue  # optional; falls back to SECRET_KEY
        if value in (_DEFAULT_SECRET_KEY, _DEV_ONLY_SECRET_KEY) or len(value) < _MIN_SECRET_LEN:
            raise RuntimeError(
                f"{name} is missing, the published placeholder, or shorter than "
                f"{_MIN_SECRET_LEN} characters (APP_ENV={s.app_env!r}). Run "
                "`./scripts/init_env.sh` to generate secrets into .env, or set "
                'it yourself: `python -c "import secrets; print(secrets.token_hex(32))"`.'
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()
    validate_settings(s)

    if not s.llm_configured:
        import warnings

        warnings.warn(
            "LLM_API_KEY is not set (GROQ_API_KEY is also accepted). "
            "Summaries will use the extractive fallback and topic extraction "
            "will use keywords. The digest still builds.",
            stacklevel=2,
        )
    return s
