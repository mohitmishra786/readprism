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
        "prune-old-full-text": {
            "task": "app.workers.tasks.prune_content.prune_old_full_text",
            "schedule": crontab(hour=3, minute=30),  # daily at 3:30 AM UTC
        },
        "precompute-prs": {
            "task": "app.workers.tasks.compute_prs.precompute_prs_for_active_users",
            # Every 2 hours so PRS scores are ready when digests are built
            "schedule": 2 * 60 * 60,
        },
        "beat-heartbeat": {
            "task": "app.workers.tasks.heartbeat.beat_heartbeat",
            "schedule": 60,  # every minute — drives the beat liveness healthcheck
        },
        "reengagement-emails": {
            "task": "app.workers.tasks.reengagement.send_reengagement_emails",
            "schedule": crontab(hour=16, minute=0),  # daily at 16:00 UTC
        },
    }
