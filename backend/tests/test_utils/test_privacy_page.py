"""The 'what we collect' page lists every recorded field (#134).

Repo-level file: skips inside the backend container and runs in CI's
"Config checks" job.
"""

from __future__ import annotations

import re

from tests.repo_files import require_repo_root

ROOT = require_repo_root()
DATA = (ROOT / "frontend" / "src" / "lib" / "collectedData.ts").read_text()


def _documented() -> dict[str, list[str]]:
    tables: dict[str, list[str]] = {}
    for block in re.split(r"\n  \{\n    table: ", DATA)[1:]:
        name = re.match(r'"([a-z_]+)"', block).group(1)
        tables[name] = re.findall(r'\{ field: "([a-z_]+)"', block)
    return tables


def test_every_telemetry_column_is_on_the_page_and_nothing_else():
    from app.models.content import UserContentInteraction
    from app.models.digest import Digest, DigestImpression
    from app.models.product_event import ProductEvent

    documented = _documented()
    for model in (UserContentInteraction, DigestImpression, Digest, ProductEvent):
        columns = [c.name for c in model.__table__.columns]
        assert sorted(documented[model.__tablename__]) == sorted(columns), model.__tablename__


def test_linked_from_onboarding_and_preferences():
    onboarding = (ROOT / "frontend/src/components/onboarding/InterestInput.tsx").read_text()
    prefs = (ROOT / "frontend/src/app/(app)/preferences/page.tsx").read_text()
    assert 'href="/privacy"' in onboarding and 'href="/privacy"' in prefs


COOKIES = (ROOT / "frontend" / "src" / "lib" / "cookies.ts").read_text()


def _listed() -> set[str]:
    return set(re.findall(r'\{ name: "([^"]+)"', COOKIES))


def test_cookie_audit_lists_every_cookie_the_api_sets():
    """#211: the API sets only the three session cookies, and all are listed."""
    from app.api import session_cookies

    app_dir = ROOT / "backend" / "app"
    setters = [
        p.relative_to(ROOT).as_posix()
        for p in app_dir.rglob("*.py")
        if "set_cookie(" in p.read_text()
    ]
    assert setters == ["backend/app/api/session_cookies.py"]
    names = {
        session_cookies.ACCESS_COOKIE,
        session_cookies.REFRESH_COOKIE,
        session_cookies.CSRF_COOKIE,
    }
    assert names <= _listed()


def test_cookie_audit_lists_every_browser_storage_key():
    src = ROOT / "frontend" / "src"
    files = [p for p in src.rglob("*.ts*") if ".test." not in p.name]
    assert not any("document.cookie" in p.read_text() for p in files)
    keys: set[str] = set()
    for p in files:
        text = p.read_text()
        consts = dict(re.findall(r'const ([A-Z_]+) = "([^"]+)"', text))
        for arg in re.findall(r"localStorage\.setItem\(([^,]+),", text):
            arg = arg.strip()
            keys.add(arg.strip('"') if arg.startswith('"') else consts[arg])
    cache = re.search(r'CACHE_VERSION = "([^"]+)"', (ROOT / "frontend/public/sw.js").read_text())
    keys.add(cache.group(1))
    assert keys and keys <= _listed(), keys - _listed()


def test_cookie_notice_linked_from_the_footer():
    shell = (ROOT / "frontend/src/components/marketing/MarketingShell.tsx").read_text()
    assert 'href="/privacy#cookies"' in shell
