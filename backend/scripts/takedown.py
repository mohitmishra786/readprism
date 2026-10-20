#!/usr/bin/env python
"""Instance-wide takedown list management (#183).

Usage:
    cd backend && python scripts/takedown.py <url-or-host> --reason "..."
    cd backend && python scripts/takedown.py <url-or-host> --remove
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Add backend directory to sys.path so app imports work when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def run_takedown(target: str, reason: str, remove: bool, host: bool | None = None) -> int:
    from app.database import AsyncSessionLocal
    from app.services.takedown import add_blocked_entry, normalize_target, remove_blocked_entry

    key = normalize_target(target, host)
    if not key:
        print("Error: Invalid URL or host target", file=sys.stderr)
        return 1

    async with AsyncSessionLocal() as session:
        if remove:
            ok = await remove_blocked_entry(session, target, host)
            await session.commit()
            if ok:
                print(f"Removed takedown entry: {key}")
                return 0
            else:
                print(f"No takedown entry found for: {key}")
                return 1
        else:
            if not reason.strip():
                print("Error: --reason is required when adding a takedown entry", file=sys.stderr)
                return 1
            entry = await add_blocked_entry(session, target, reason, host)
            await session.commit()
            print(f"Added takedown entry: {entry.url_key} (reason: {entry.reason})")
            return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage instance-wide takedowns")
    parser.add_argument("target", help="URL or hostname to block/unblock")
    parser.add_argument("--reason", default="", help="Reason for takedown request")
    parser.add_argument("--remove", action="store_true", help="Remove an existing entry")
    parser.add_argument(
        "--host", action="store_true", default=None, help="Force treating target as a whole host"
    )

    args = parser.parse_args()
    return asyncio.run(run_takedown(args.target, args.reason, args.remove, args.host))


if __name__ == "__main__":
    sys.exit(main())
