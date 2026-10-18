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
        "learn-send-times": {
            "task": "app.workers.tasks.build_digest.learn_send_times",
            "schedule": crontab(hour=3, minute=15, day_of_week=0),  # weekly, Sun 03:15 UTC
        },
        "prune-old-full-text": {
            "task": "app.workers.tasks.prune_content.prune_old_full_text",
            "schedule": crontab(hour=3, minute=30),  # daily at 3:30 AM UTC
        },
        "repair-missing-embeddings": {
            "task": "app.workers.tasks.compute_embeddings.repair_missing_embeddings",
            "schedule": 30 * 60,
        },
        "prune-raw-telemetry": {
            "task": "app.workers.tasks.prune_telemetry.prune_raw_telemetry",
            "schedule": crontab(hour=3, minute=45),  # daily, after the full-text prune
        },
        "refresh-discovery-pools": {
            "task": "app.workers.tasks.discovery.refresh_discovery_pools",
            "schedule": crontab(hour=4, minute=30),  # daily, before morning digests
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
