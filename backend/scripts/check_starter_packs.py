"""Starter-pack liveness check (CS-02): >= 90% of pack feeds must respond.

Run:  cd backend && PYTHONPATH=. python3 scripts/check_starter_packs.py
Exit 0 when the live ratio is >= 90%; exit 1 otherwise, listing dead feeds.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.cold_start.starter_packs import list_starter_packs

UA = "ReadPrism/1.0 (+https://readprism.app/bot) starter-pack-liveness"
TIMEOUT = 15.0
MIN_LIVE_RATIO = 0.90


async def check_feed(client: httpx.AsyncClient, url: str) -> bool:
    try:
        resp = await client.get(url, headers={"User-Agent": UA})
        return resp.status_code < 400
    except Exception:
        return False


async def main() -> int:
    packs = list_starter_packs()
    print(f"checking {len(packs)} packs…")
    dead: list[str] = []
    total = 0
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        for pack in packs:
            results = await asyncio.gather(
                *(check_feed(client, feed["feed_url"]) for feed in pack.feeds)
            )
            pack_dead = [
                feed["feed_url"] for feed, ok in zip(pack.feeds, results, strict=True) if not ok
            ]
            total += len(pack.feeds)
            dead.extend(pack_dead)
            status = "OK" if not pack_dead else f"{len(pack_dead)} dead"
            print(f"  {pack.id}: {len(pack.feeds)} feeds — {status}")
            for url in pack_dead:
                print(f"    DEAD {url}")

    live_ratio = (total - len(dead)) / total if total else 0.0
    print(f"\n{total - len(dead)}/{total} feeds live ({live_ratio:.1%})")
    if live_ratio < MIN_LIVE_RATIO:
        print(f"FAIL: below the {MIN_LIVE_RATIO:.0%} liveness gate")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
