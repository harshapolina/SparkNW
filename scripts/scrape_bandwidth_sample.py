"""Scrape exactly 10 profiles and print bandwidth/pagination metrics.

Does NOT enqueue the full roster. Usage:

  python scripts/scrape_bandwidth_sample.py
  python scripts/scrape_bandwidth_sample.py --limit 10
  python scripts/scrape_bandwidth_sample.py niat.genai user2 user3
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scraper"))
sys.path.insert(0, str(ROOT / "packages" / "python-shared"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("pymongo").setLevel(logging.WARNING)


def _load_usernames(limit: int, explicit: list[str]) -> list[str]:
    names = [n.strip().lstrip("@") for n in explicit if n.strip()]
    if len(names) >= limit:
        return names[:limit]
    env_list = (os.getenv("SCRAPE_TEST_USERNAMES") or "").strip()
    if env_list:
        names.extend(n.strip().lstrip("@") for n in env_list.split(",") if n.strip())
    names = list(dict.fromkeys(names))
    if len(names) >= limit:
        return names[:limit]
    try:
        from pymongo import MongoClient

        env: dict[str, str] = {}
        for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
        uri = os.environ.get("MONGODB_URI") or env.get("MONGODB_URI")
        dbn = os.environ.get("MONGODB_DB") or env.get("MONGODB_DB") or "instascope"
        if not uri:
            raise RuntimeError("MONGODB_URI missing")
        client = MongoClient(uri, serverSelectionTimeoutMS=20000)
        cur = (
            client[dbn]
            .profiles.find({"username": {"$exists": True, "$ne": ""}}, {"username": 1})
            .limit(limit * 3)
        )
        for doc in cur:
            u = str(doc.get("username") or "").strip().lstrip("@")
            if u and u not in names:
                names.append(u)
            if len(names) >= limit:
                break
    except Exception as exc:
        print(f"mongo username load skipped: {exc}", file=sys.stderr)
    return names[:limit]


async def main() -> None:
    ap = argparse.ArgumentParser(description="Bandwidth sample scrape (default 10 profiles)")
    ap.add_argument("usernames", nargs="*", help="Optional explicit handles")
    ap.add_argument("--limit", type=int, default=int(os.getenv("SCRAPE_TEST_LIMIT") or "10"))
    args = ap.parse_args()
    limit = max(1, min(args.limit, 10))
    handles = _load_usernames(limit, args.usernames)
    if not handles:
        raise SystemExit("No usernames. Pass handles or set MONGODB_URI.")

    from instascope_scraper.profile import scrape_profile
    from instascope_scraper.proxy_pool import next_proxy
    from instascope_scraper.types import parse_proxy_url

    proxy = next_proxy() or parse_proxy_url(os.getenv("SCRAPE_PROXY_URL") or None)
    print(f"Profiles to scrape: {len(handles)} (cap={limit})")
    summaries: list[dict] = []
    ok = fail = 0
    posts = req = pag = retries = bytes_rx = 0.0

    for handle in handles:
        print(f"--- scraping @{handle} ---")
        try:
            result = await scrape_profile(
                handle, headless=True, proxy=proxy, delay_seconds=1.0, live=True
            )
            metrics = (result.raw or {}).get("scrape_metrics") or {}
            ok += 1
            nposts = len(result.posts or [])
            posts += nposts
            req += float(metrics.get("total_requests") or 0)
            pag += float(metrics.get("pagination_requests") or 0)
            retries += float(metrics.get("retry_count") or 0)
            bytes_rx += float(metrics.get("bytes_received") or 0)
            summaries.append(
                {
                    "username": handle,
                    "ok": True,
                    "posts": nposts,
                    "path": (result.raw or {}).get("path"),
                    **{k: metrics.get(k) for k in (
                        "total_requests",
                        "pagination_requests",
                        "retry_count",
                        "bytes_received",
                        "scrape_duration_s",
                        "blocked_requests",
                    )},
                }
            )
            print(
                f"OK @{handle} posts={nposts} req={metrics.get('total_requests')} "
                f"bytes={metrics.get('bytes_received')} path={(result.raw or {}).get('path')}"
            )
        except Exception as exc:
            fail += 1
            summaries.append({"username": handle, "ok": False, "error": str(exc)[:240]})
            print(f"FAIL @{handle}: {exc}")

    n = max(len(handles), 1)
    gb = bytes_rx / (1024 ** 3)
    print("")
    print("========== SAMPLE SUMMARY ==========")
    print(f"Profiles: {len(handles)}")
    print(f"Successful: {ok}")
    print(f"Failed: {fail}")
    print(f"Posts collected: {int(posts)}")
    print(f"Total requests: {int(req)}")
    print(f"Pagination requests: {int(pag)}")
    print(f"Retries: {int(retries)}")
    print(f"Bytes received: {int(bytes_rx)} ({gb:.4f} GB)")
    print(f"Average requests/profile: {req / n:.1f}")
    print(f"Average posts/profile: {posts / n:.1f}")
    print(f"GB/profile: {gb / n:.4f}")
    print("====================================")


if __name__ == "__main__":
    asyncio.run(main())
