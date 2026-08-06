"""Run full scrape_profile and print post counts (enrich capped for speed)."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scraper"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

# Cap enrich so we can verify timeline collection quickly
os.environ["SCRAPE_ENRICH_MAX"] = "3"
os.environ["SCRAPE_MAX_RETRIES"] = "1"

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


async def main() -> None:
    from instascope_scraper.profile import scrape_profile

    uname = sys.argv[1] if len(sys.argv) > 1 else "niat.genai"
    print(f"scraping @{uname} ...")
    try:
        result = await scrape_profile(uname, headless=True, proxy=None, delay_seconds=1.0, live=True)
    except Exception:
        traceback.print_exc()
        return
    print(
        f"DONE @{result.username} posts={len(result.posts)}/{result.posts_count} "
        f"followers={result.followers} path={(result.raw or {}).get('path')} "
        f"private={result.is_private}"
    )


if __name__ == "__main__":
    asyncio.run(main())
