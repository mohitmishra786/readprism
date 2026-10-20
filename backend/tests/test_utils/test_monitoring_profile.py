"""The optional monitoring profile and its dashboard (#170).

Repo-level file: skips inside the backend container and runs in CI's
"Config checks" job.
"""

from __future__ import annotations

import json
import re

import yaml

from tests.repo_files import require_repo_root

ROOT = require_repo_root()
MON = ROOT / "deploy" / "monitoring"


def test_profile_is_off_by_default():
    services = yaml.safe_load((ROOT / "docker-compose.yml").read_text())["services"]
    for name in ("prometheus", "grafana"):
        assert services[name]["profiles"] == ["monitoring"], name


def test_dashboard_queries_only_exported_series():
    exported = set(
        re.findall(
            r'"(readprism_[a-z0-9_]+)"',
            (ROOT / "backend/app/services/metrics/prometheus.py").read_text(),
        )
    )
    # Counters gain _total; histograms expose _bucket/_sum/_count.
    known = exported | {f"{n}_total" for n in exported} | {f"{n}_bucket" for n in exported}
    dashboard = json.loads((MON / "grafana/dashboards/readprism.json").read_text())
    used = {
        name
        for panel in dashboard["panels"]
        for target in panel["targets"]
        for name in re.findall(r"readprism_[a-z0-9_]+", target["expr"])
    }
    assert used and used <= known, used - known
    titles = " ".join(p["title"] for p in dashboard["panels"]).lower()
    for series in ("latency", "queue", "ingested", "feed health", "digest build", "llm"):
        assert series in titles, series


def test_prometheus_scrapes_the_api_with_the_token():
    config = yaml.safe_load((MON / "prometheus.yml").read_text())
    job = config["scrape_configs"][0]
    assert job["static_configs"][0]["targets"] == ["backend:8000"]
    assert job["authorization"]["credentials_file"] == "/tmp/metrics_token"
