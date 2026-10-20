from __future__ import annotations

from celery import Celery, signals

from app.config import get_settings
from app.utils.observability import init_sentry

settings = get_settings()


@signals.worker_process_init.connect
def _init_worker_sentry(**_kwargs) -> None:
    # Initialize per worker/beat process so uncaught task errors are reported.
    init_sentry("worker")


@signals.task_prerun.connect
def _refresh_instance_settings(**_kwargs) -> None:
    # Pick up LLM / SMTP settings saved on the setup screen (#220), at most
    # once a minute and only when secrets can be stored at all.
    from app.utils import secretbox

    if not secretbox.configured():
        return
    import asyncio

    try:
        asyncio.get_running_loop()
        return  # eager / in-loop execution (tests): nothing to refresh
    except RuntimeError:
        pass
    from app.services.instance_config import refresh_in_worker

    refresh_in_worker()


@signals.beat_init.connect
def _init_beat_sentry(**_kwargs) -> None:
    init_sentry("beat")


celery_app = Celery(
    "readprism",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.workers.tasks.ingest_feeds",
        "app.workers.tasks.compute_embeddings",
        "app.workers.tasks.build_digest",
        "app.workers.tasks.deliver_digest",
        "app.workers.tasks.update_interest_graph",
        "app.workers.tasks.prune_content",
        "app.workers.tasks.prune_telemetry",
        "app.workers.tasks.heartbeat",
        "app.workers.tasks.reengagement",
        "app.workers.tasks.trial_emails",
        "app.workers.tasks.discovery",
        "app.workers.tasks.import_jobs",
        "app.workers.tasks.weekly_learning",
        "app.workers.tasks.alerts",
    ],
)

# Route tasks to dedicated queues so a slow scrape can't block embeddings or
# digest delivery on the same solo worker (audit 07-2). One worker container per
# queue consumes these; the digest worker also drains the default queue.
celery_app.conf.task_routes = {
    "app.workers.tasks.ingest_feeds.*": {"queue": "scrape"},
    "app.workers.tasks.compute_embeddings.*": {"queue": "embed"},
    "app.workers.tasks.build_digest.*": {"queue": "digest"},
    "app.workers.tasks.deliver_digest.*": {"queue": "digest"},
    "app.workers.tasks.update_interest_graph.*": {"queue": "digest"},
    "app.workers.tasks.prune_content.*": {"queue": "digest"},
    "app.workers.tasks.prune_telemetry.*": {"queue": "digest"},
    "app.workers.tasks.heartbeat.*": {"queue": "digest"},
    "app.workers.tasks.reengagement.*": {"queue": "digest"},
    "app.workers.tasks.trial_emails.*": {"queue": "digest"},
    "app.workers.tasks.discovery.*": {"queue": "scrape"},
    "app.workers.tasks.import_jobs.*": {"queue": "digest"},
    "app.workers.tasks.weekly_learning.*": {"queue": "digest"},
    # Scheduled on scrape and digest explicitly (see the beat schedule).
    "app.workers.tasks.alerts.*": {"queue": "digest"},
}

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
)

# Import schedules (beat config is set in schedules.py)
import app.workers.queue_metrics  # noqa: F401  (signal handlers, #239)
from app.workers.schedules import setup_beat_schedule

setup_beat_schedule(celery_app)
