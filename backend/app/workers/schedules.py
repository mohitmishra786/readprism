from __future__ import annotations

from celery import Celery
from celery.schedules import crontab


def setup_beat_schedule(app: Celery) -> None:
    app.conf.beat_schedule = {
        "ingest-feeds": {
            "task": "app.workers.tasks.ingest_feeds.ingest_all_feeds",
            "schedule": 30 * 60,  # every 30 minutes
        },
        "ingest-creator-feeds": {
            "task": "app.workers.tasks.ingest_feeds.ingest_creator_feeds",
            "schedule": 60 * 60,  # every 60 minutes
        },
        "schedule-daily-digests": {
            "task": "app.workers.tasks.build_digest.schedule_daily_digests",
            # Run every 30 minutes so per-user timezone checks fire at the right local time.
            "schedule": 30 * 60,
        },
        "apply-decay": {
            "task": "app.workers.tasks.update_interest_graph.apply_decay_all_users",
            "schedule": crontab(hour=2, minute=0),  # daily at 2:00 AM UTC
        },
        "precompute-prs": {
            "task": "app.workers.tasks.compute_prs.precompute_prs_for_active_users",
            # Every 2 hours so PRS scores are ready when digests are built
            "schedule": 2 * 60 * 60,
        },
    }
