"""Verify username-feed full timeline under rate-limit conditions."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scraper"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
os.environ["SCRAPE_ENRICH_MAX"] = "2"
os.environ["SCRAPE_MAX_RETRIES"] = "2"
os.environ["SCRAPE_HTTP_RETRIES"] = "4"
os.environ["SCRAPE_WEB_PROFILE_RETRIES"] = "1"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)


async def main() -> None:
    from instascope_scraper.http_profile import fetch_timeline_via_username_feed
    from instascope_scraper.profile import scrape_profile

    uname = sys.argv[1] if len(sys.argv) > 1 else "yours.tej"
    expected = int(sys.argv[2]) if len(sys.argv) > 2 else 0

    print(f"--- username feed @{uname} ---")
    user, nodes = await fetch_timeline_via_username_feed(uname, expected_count=expected)
    mc = (user or {}).get("media_count")
    print(f"FEED user={bool(user)} media_count={mc} nodes={len(nodes)} uid={(user or {}).get('pk') or (user or {}).get('id')}")

    print(f"--- scrape_profile @{uname} ---")
    result = await scrape_profile(uname, headless=True, proxy=None, delay_seconds=1.0, live=True)
    print(
        f"SCRAPE posts={len(result.posts)}/{result.posts_count} "
        f"path={(result.raw or {}).get('path')} followers={result.followers}"
    )
    ok = len(result.posts) >= (
        result.posts_count if result.posts_count <= 12 else max(result.posts_count - 2, 1)
    )
    print("PASS" if ok else "FAIL")
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
