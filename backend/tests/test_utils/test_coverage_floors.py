"""The CI coverage gate fails on a regression (#189)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_coverage.py"
spec = importlib.util.spec_from_file_location("check_coverage", SCRIPT)
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def _report(**pcts):
    return {
        "totals": {"percent_covered": 90.0},
        "files": {p: {"summary": {"percent_covered": v}} for p, v in pcts.items()},
    }


def test_passes_at_or_above_every_floor():
    report = _report(**dict(check.FLOORS))
    assert check.failures(report) == []


def test_a_drop_below_a_module_floor_fails():
    pcts = {p: 100.0 for p in check.FLOORS}
    pcts["app/services/ranking/ranker.py"] = 60.0
    problems = check.failures(_report(**pcts))
    assert problems == ["app/services/ranking/ranker.py: 60.0% < floor 95%"]


def test_a_renamed_hot_path_is_flagged_not_silently_skipped():
    pcts = {p: 100.0 for p in check.FLOORS if p != "app/api/feedback.py"}
    assert check.failures(_report(**pcts)) == [
        "app/api/feedback.py: not measured (renamed or deleted? update FLOORS)"
    ]


def test_cli_exit_codes(tmp_path):
    import json

    ok = tmp_path / "ok.json"
    ok.write_text(json.dumps(_report(**{p: 100.0 for p in check.FLOORS})))
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(_report(**{p: 1.0 for p in check.FLOORS})))
    assert check.main(["x", str(ok)]) == 0
    assert check.main(["x", str(bad)]) == 1
