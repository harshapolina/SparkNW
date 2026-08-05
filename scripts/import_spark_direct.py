#!/usr/bin/env python3
"""Import SPARK TSV directly into MongoDB Atlas (bypasses API student-field deploy).

Creates/updates profiles under sparkadmin, then optionally queues scrapes via prod API.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "python-shared"))

import importlib.util

_roster_path = ROOT / "packages" / "python-shared" / "instascope_shared" / "services" / "student_roster.py"
_spec = importlib.util.spec_from_file_location("student_roster", _roster_path)
_roster = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_roster)
map_sheet_row = _roster.map_sheet_row
merge_student = _roster.merge_student

from instascope_shared.domain.instagram import extract_username  # noqa: E402

from pymongo import MongoClient, UpdateOne

ADMIN_EMAIL = "sparkadmin@nw.co.in"
ADMIN_PASSWORD = "Editco@spark3"


def load_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def load_tsv(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    reader = csv.reader(io.StringIO(text), delimiter="\t", quotechar='"')
    rows = list(reader)
    if not rows:
        return []
    headers = [h.strip() for h in rows[0]]
    out: list[dict] = []
    seen: set[str] = set()
    for values in rows[1:]:
        if not any(str(v).strip() for v in values):
            continue
        mapped = map_sheet_row(headers, values)
        url = mapped["url"]
        if not url:
            continue
        try:
            username = extract_username(url)
        except ValueError:
            continue
        key = username.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"username": username, "url": f"https://www.instagram.com/{username}", "student": mapped["student"]})
    return out


def http_json(method: str, url: str, body: dict | None = None, token: str | None = None) -> dict | list:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} -> {e.code}: {detail}") from e


def login(api: str) -> str:
    res = http_json("POST", f"{api}/auth/login", {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    if isinstance(res, dict):
        if res.get("access_token"):
            return res["access_token"]
        tokens = res.get("tokens") or {}
        if tokens.get("access_token"):
            return tokens["access_token"]
    raise RuntimeError(f"login failed: {res}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsv", default=str(ROOT / "data" / "spark_students.tsv"))
    ap.add_argument("--api", default="http://62.238.57.52:8000/api/v1")
    ap.add_argument("--mongo-uri", default="", help="Override MONGODB_URI (use prod Atlas for server)")
    ap.add_argument("--mongo-db", default="", help="Override MONGODB_DB")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--scrape", action="store_true", help="Queue scrapes via production API after import")
    ap.add_argument("--scrape-only", action="store_true", help="Skip Mongo import; only call refresh API")
    ap.add_argument("--scrape-chunk", type=int, default=40)
    ap.add_argument("--limit", type=int, default=0, help="Max profiles to scrape (0=all)")
    args = ap.parse_args()

    env = load_dotenv(ROOT / ".env")
    uri = args.mongo_uri or os.environ.get("MONGODB_URI") or env.get("MONGODB_URI")
    db_name = args.mongo_db or os.environ.get("MONGODB_DB") or env.get("MONGODB_DB") or "instascope"
    if not uri:
        print("MONGODB_URI missing", file=sys.stderr)
        return 1

    profiles = load_tsv(Path(args.tsv))
    print(f"Parsed {len(profiles)} unique Instagram profiles from TSV")

    if args.dry_run:
        for p in profiles[:5]:
            print(" sample:", p["username"], p["student"].get("full_name"), p["student"].get("university"))
        return 0

    client = MongoClient(uri, serverSelectionTimeoutMS=15000)
    db = client[db_name]
    user = db.users.find_one({"email": re.compile(f"^{re.escape(ADMIN_EMAIL)}$", re.I)})
    if not user:
        print(f"Admin user {ADMIN_EMAIL} not found in {db_name}.users — create via API first", file=sys.stderr)
        return 1
    user_id = str(user["_id"])
    print(f"Using admin user_id={user_id} email={user.get('email')}")

    if not args.scrape_only:
        now = datetime.now(timezone.utc)
        ops: list[UpdateOne] = []
        for p in profiles:
            student = merge_student({}, p["student"])
            ops.append(
                UpdateOne(
                    {"user_id": user_id, "username": p["username"]},
                    [
                        {
                            "$set": {
                                "user_id": user_id,
                                "username": p["username"],
                                "profile_url": p["url"],
                                "updated_at": now,
                                "student": {
                                    "$mergeObjects": [
                                        {"$ifNull": ["$student", {}]},
                                        student,
                                    ]
                                },
                                "followers": {"$ifNull": ["$followers", 0]},
                                "following": {"$ifNull": ["$following", 0]},
                                "posts_count": {"$ifNull": ["$posts_count", 0]},
                                "avg_likes": {"$ifNull": ["$avg_likes", 0.0]},
                                "avg_views": {"$ifNull": ["$avg_views", 0.0]},
                                "avg_comments": {"$ifNull": ["$avg_comments", 0.0]},
                                "engagement_rate": {"$ifNull": ["$engagement_rate", 0.0]},
                                "growth_pct_today": {"$ifNull": ["$growth_pct_today", 0.0]},
                                "is_private": {"$ifNull": ["$is_private", False]},
                                "is_business": {"$ifNull": ["$is_business", False]},
                                "is_verified": {"$ifNull": ["$is_verified", False]},
                                "highlight_reel_count": {"$ifNull": ["$highlight_reel_count", 0]},
                                "follower_following_ratio": {"$ifNull": ["$follower_following_ratio", 0.0]},
                                "insights": {"$ifNull": ["$insights", {}]},
                                "status": {"$ifNull": ["$status", "active"]},
                                "created_at": {"$ifNull": ["$created_at", now]},
                            }
                        }
                    ],
                    upsert=True,
                )
            )

        result = db.profiles.bulk_write(ops, ordered=False)
        print(
            f"Mongo upsert done: matched={result.matched_count} "
            f"modified={result.modified_count} upserted={len(result.upserted_ids)}"
        )

    count = db.profiles.count_documents({"user_id": user_id, "student": {"$exists": True, "$ne": {}}})
    print(f"Profiles with student data for admin: {count}")

    if not args.scrape and not args.scrape_only:
        print("Skipping scrape queue (pass --scrape or --scrape-only)")
        return 0

    token = login(args.api)
    # Prefer unscraped first; prod bulk/refresh returns 500, so use single refresh.
    cursor = db.profiles.find(
        {"user_id": user_id, "student.full_name": {"$exists": True}},
        {"_id": 1, "username": 1, "last_success_at": 1},
    ).sort([("last_success_at", 1)])
    rows = list(cursor)
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]
    print(f"Queueing scrape for {len(rows)} profiles via {args.api} (single /refresh)")
    ok = fail = 0
    for i, doc in enumerate(rows, start=1):
        pid = str(doc["_id"])
        username = doc.get("username") or pid
        try:
            res = http_json("POST", f"{args.api}/profiles/{pid}/refresh", token=token)
            status = ""
            if isinstance(res, list) and res:
                status = str(res[0].get("status") or "")
            elif isinstance(res, dict):
                status = str(res.get("status") or "")
            ok += 1
            print(f"  [{i}/{len(rows)}] {username} -> {status or 'ok'}", flush=True)
        except RuntimeError as e:
            fail += 1
            print(f"  [{i}/{len(rows)}] {username} FAILED: {e}", file=sys.stderr, flush=True)
            # Refresh token once on auth errors
            if "401" in str(e) or "403" in str(e):
                try:
                    token = login(args.api)
                except Exception:
                    pass
    print(f"Scrape finished: ok={ok} fail={fail}")
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
