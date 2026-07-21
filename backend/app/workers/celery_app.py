from __future__ import annotations

from celery import Celery, signals

from app.config import get_settings
from app.utils.observability import init_sentry

settings = get_settings()


@signals.worker_process_init.connect
def _init_worker_sentry(**_kwargs) -> None:
    # Initialize per worker/beat process so uncaught task errors are reported.
    init_sentry("worker")


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
        "app.workers.tasks.compute_prs",
        "app.workers.tasks.build_digest",
        "app.workers.tasks.deliver_digest",
        "app.workers.tasks.update_interest_graph",
        "app.workers.tasks.prune_content",
        "app.workers.tasks.heartbeat",
    ],
)

# Route tasks to dedicated queues so a slow scrape can't block embeddings or
# digest delivery on the same solo worker (audit 07-2). One worker container per
# queue consumes these; the digest worker also drains the default queue.
celery_app.conf.task_routes = {
    "app.workers.tasks.ingest_feeds.*": {"queue": "scrape"},
    "app.workers.tasks.compute_embeddings.*": {"queue": "embed"},
    "app.workers.tasks.compute_prs.*": {"queue": "digest"},
    "app.workers.tasks.build_digest.*": {"queue": "digest"},
    "app.workers.tasks.deliver_digest.*": {"queue": "digest"},
    "app.workers.tasks.update_interest_graph.*": {"queue": "digest"},
    "app.workers.tasks.prune_content.*": {"queue": "digest"},
    "app.workers.tasks.heartbeat.*": {"queue": "digest"},
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
from app.workers.schedules import setup_beat_schedule

setup_beat_schedule(celery_app)
