"""Error tracking via Sentry (audit 07-1).

Opt-in: with no `SENTRY_DSN` set this is a no-op, so self-hosters and CI run
without it. Called from both runtimes — the FastAPI app (API) and the Celery
worker/beat — so digest/ingestion failures are no longer invisible.
"""

from __future__ import annotations

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


def init_sentry(component: str) -> bool:
    """Initialize Sentry for a runtime component ('api' | 'worker' | 'beat').

    Returns True if enabled. Integrations are auto-detected by the SDK (FastAPI,
    Celery), so we only pass DSN, environment, sample rate, and a component tag.
    """
    settings = get_settings()
    if not settings.sentry_dsn:
        return False
    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.app_env,
            traces_sample_rate=settings.sentry_traces_sample_rate,
            send_default_pii=False,
        )
        sentry_sdk.set_tag("component", component)
        logger.info(f"Sentry error tracking enabled for {component}")
        return True
    except Exception as e:  # pragma: no cover - never let telemetry break boot
        logger.warning(f"Failed to initialize Sentry: {e}")
        return False
