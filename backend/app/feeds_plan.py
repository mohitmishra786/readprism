"""Preview the shared-feeds migration (#163) without changing anything.

    python -m app.feeds_plan

Prints how many subscriptions merge into each shared feed, so an operator
can see the effect of migration 0025 before upgrading (run `make backup`
first either way).
"""

from __future__ import annotations

import sys

from sqlalchemy import create_engine, text


def plan(url: str) -> list[tuple[str, int]]:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT coalesce(feed_url, url) AS key, count(*) AS subscribers
                    FROM sources
                    WHERE source_type IS DISTINCT FROM 'newsletter'
                    GROUP BY 1
                    ORDER BY 2 DESC, 1
                    """
                )
            ).all()
    finally:
        engine.dispose()
    return [(row[0], int(row[1])) for row in rows]


def main() -> int:
    from app.config import get_settings

    rows = plan(get_settings().database_sync_url)
    shared = [r for r in rows if r[1] > 1]
    total = sum(n for _, n in rows)
    print(f"{total} subscriptions -> {len(rows)} feeds ({len(shared)} shared by 2+ users)")
    for key, n in shared[:50]:
        print(f"  {n:>4}  {key}")
    if len(shared) > 50:
        print(f"  ... and {len(shared) - 50} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
