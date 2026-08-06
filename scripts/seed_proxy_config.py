#!/usr/bin/env python3
"""Seed Decodo proxy settings into MongoDB Atlas for the cloud API.

Cloud Docker was wiping SCRAPE_PROXY_* via empty compose defaults. After this
seed + deploy, the API loads proxies from the `app_config` collection.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "python-shared"))

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(ROOT / ".env")


def main() -> int:
    uri = os.getenv("MONGODB_URI")
    db_name = os.getenv("MONGODB_DB") or "instascope"
    if not uri:
        print("MONGODB_URI missing", file=sys.stderr)
        return 1

    host = os.getenv("SCRAPE_PROXY_HOST") or "gate.decodo.com"
    user = os.getenv("SCRAPE_PROXY_USER")
    password = os.getenv("SCRAPE_PROXY_PASS")
    ports = os.getenv("SCRAPE_PROXY_PORTS") or "7000,10001,10002,10003,10004,10005,10006,10007"
    if not user or password is None:
        print("SCRAPE_PROXY_USER / SCRAPE_PROXY_PASS missing in .env", file=sys.stderr)
        return 1

    data = {
        "host": host,
        "user": user,
        "password": password,
        "ports": ports,
        "scheme": os.getenv("SCRAPE_PROXY_SCHEME") or "http",
        "user_prefix": os.getenv("SCRAPE_PROXY_USER_PREFIX")
        if os.getenv("SCRAPE_PROXY_USER_PREFIX") is not None
        else "user-",
        "session_rotate": os.getenv("SCRAPE_PROXY_SESSION_ROTATE") or "1",
        "url": os.getenv("SCRAPE_PROXY_URL") or "",
        "urls": os.getenv("SCRAPE_PROXY_URLS") or "",
    }

    client = MongoClient(uri, serverSelectionTimeoutMS=15000)
    db = client[db_name]
    now = datetime.now(timezone.utc)
    db.app_config.update_one(
        {"key": "scrape_proxy"},
        {"$set": {"key": "scrape_proxy", "data": data, "updated_at": now}},
        upsert=True,
    )
    print(
        f"OK seeded app_config.scrape_proxy host={host} user={user} ports={ports}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
