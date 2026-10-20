#!/usr/bin/env python
"""Override one hosted account's plan quotas (#172).

    cd backend && python scripts/set_quota.py reader@example.com sources=1000 llm_summaries_per_day=500
    python scripts/set_quota.py reader@example.com sources=        # drop one override
    python scripts/set_quota.py reader@example.com --clear          # drop all
    python scripts/set_quota.py reader@example.com                  # show

Quotas: sources, creators, newsletters_per_day, newsletter_mb_per_day,
llm_summaries_per_day, digest_builds_per_day. 0 = unlimited.
"""

from __future__ import annotations

import asyncio
import sys


async def main(email: str, args: list[str]) -> int:
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.user import User
    from app.services.entitlements import QUOTAS, limit

    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is None:
            print(f"no account {email}")
            return 1
        overrides = dict(user.quota_overrides or {})
        for arg in args:
            if arg == "--clear":
                overrides = {}
                continue
            name, _, value = arg.partition("=")
            if name not in QUOTAS:
                print(f"unknown quota {name!r}; one of {', '.join(QUOTAS)}")
                return 1
            if value == "":
                overrides.pop(name, None)
            else:
                overrides[name] = int(value)
        if args:
            user.quota_overrides = overrides or None
            await session.commit()
        for name in QUOTAS:
            mark = " (override)" if name in overrides else ""
            print(f"{name}: {limit(user, name) or 'unlimited'}{mark}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(asyncio.run(main(sys.argv[1], sys.argv[2:])))
