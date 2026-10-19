"""The browser extension asks for no broad host access (#214).

Repo-level file: skips inside the backend container and runs in CI's
"Config checks" job.
"""

from __future__ import annotations

import json

from tests.repo_files import require_repo_root

ROOT = require_repo_root()
MANIFEST = json.loads((ROOT / "extension" / "manifest.json").read_text())
BROAD = {"<all_urls>", "*://*/*", "http://*/*", "https://*/*"}


def test_no_all_urls_equivalent_permission():
    granted = set(MANIFEST.get("host_permissions", [])) | set(MANIFEST.get("permissions", []))
    assert not granted & BROAD, granted & BROAD
    assert all("*." not in p.split("//", 1)[-1].split("/")[0] for p in MANIFEST["host_permissions"])


def test_no_content_script_on_every_page():
    for script in MANIFEST.get("content_scripts", []):
        assert not set(script.get("matches", [])) & BROAD


def test_instance_access_is_requested_at_setup_and_detection_runs_on_click():
    assert set(MANIFEST.get("optional_host_permissions", [])) <= BROAD  # granted per origin
    assert {"activeTab", "scripting"} <= set(MANIFEST["permissions"])
    popup = (ROOT / "extension" / "popup.js").read_text()
    options = (ROOT / "extension" / "options.js").read_text()
    assert "chrome.scripting.executeScript" in popup and '"detect-feed.js"' in popup
    assert "chrome.permissions.request" in options


def test_no_hard_coded_unlaunched_domain():
    assert not any("readprism.app/" in p for p in MANIFEST.get("host_permissions", []))
