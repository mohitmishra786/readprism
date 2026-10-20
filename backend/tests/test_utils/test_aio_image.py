"""The all-in-one image keeps the multi-container process layout (#208).

Repo-level file: skips inside the backend container and runs in CI's
"Config checks" job.
"""

from __future__ import annotations

import re

import yaml

from tests.repo_files import require_repo_root

ROOT = require_repo_root()
S6 = ROOT / "deploy" / "aio" / "rootfs" / "etc" / "s6-overlay" / "s6-rc.d"


def _runs() -> dict[str, str]:
    return {d.name: (d / "run").read_text() for d in S6.iterdir() if (d / "run").is_file()}


def test_one_worker_per_queue_and_a_single_beat():
    runs = _runs()
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())["services"]
    for name in ("worker-scrape", "worker-embed", "worker-digest"):
        queues = re.search(r"-Q (\S+)", compose[name]["command"]).group(1)
        assert f"-Q {queues} " in runs[name], name
        assert "--pool=solo" in runs[name]
    assert sum("celery_app beat" in r for r in runs.values()) == 1
    assert set(runs) == {"api", "worker-scrape", "worker-embed", "worker-digest", "beat", "web"}


def test_everything_waits_for_migrations_and_is_enabled():
    enabled = {p.name for p in (S6 / "user" / "contents.d").iterdir()}
    assert enabled == set(_runs()) | {"migrate"}
    for name in _runs():
        assert (S6 / name / "dependencies.d" / "migrate").exists(), name
    assert (S6 / "migrate" / "type").read_text().strip() == "oneshot"


def test_healthcheck_covers_every_process():
    check = (
        ROOT / "deploy" / "aio" / "rootfs" / "usr" / "local" / "bin" / "aio-healthcheck"
    ).read_text()
    for name in _runs():
        assert name in check, name
    assert "beat:heartbeat" in check


def test_compose_aio_is_three_containers():
    services = yaml.safe_load((ROOT / "compose.aio.yml").read_text())["services"]
    assert set(services) == {"readprism", "db", "redis"}
