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

    documented = _documented()
    for model in (UserContentInteraction, DigestImpression, Digest):
        columns = [c.name for c in model.__table__.columns]
        assert sorted(documented[model.__tablename__]) == sorted(columns), model.__tablename__


def test_linked_from_onboarding_and_preferences():
    onboarding = (ROOT / "frontend/src/components/onboarding/InterestInput.tsx").read_text()
    prefs = (ROOT / "frontend/src/app/(app)/preferences/page.tsx").read_text()
    assert 'href="/privacy"' in onboarding and 'href="/privacy"' in prefs
