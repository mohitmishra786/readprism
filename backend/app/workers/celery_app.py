from __future__ import annotations

from celery import Celery

from app.config import get_settings

settings = get_settings()

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
    ],
)

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
