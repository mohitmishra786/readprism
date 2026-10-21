"""Workers must not pool asyncpg connections across event loops."""

from sqlalchemy.pool import NullPool

from app.database import pool_options


def test_celery_processes_do_not_pool():
    for argv in (
        ["/usr/local/bin/celery", "-A", "app.workers.celery_app", "worker", "-Q", "embed"],
        ["celery", "-A", "app.workers.celery_app", "beat"],
    ):
        assert pool_options(argv, "auto", 10, 10) == {"poolclass": NullPool}


def test_api_pools_and_settings_override():
    api = ["/usr/local/bin/uvicorn", "app.main:app"]
    assert pool_options(api, "auto", 5, 3) == {"pool_size": 5, "max_overflow": 3}
    assert pool_options(api, "none", 5, 3) == {"poolclass": NullPool}
    worker = ["celery", "-A", "app.workers.celery_app", "worker"]
    assert pool_options(worker, "queue", 5, 3) == {"pool_size": 5, "max_overflow": 3}
