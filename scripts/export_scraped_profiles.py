#!/usr/bin/env python3
"""Export the 488 profiles that existed in Mongo before the 17 Aug roster import."""

from __future__ import annotations

import csv
import re
from datetime import datetime, timezone
from pathlib import Path

from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "data" / "scraped_profiles_488.csv"
IMPORT_CUTOFF = datetime(2026, 8, 17, tzinfo=timezone.utc)


def load_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def iso(dt) -> str:
    if not dt:
        return ""
    if getattr(dt, "tzinfo", None):
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def main() -> int:
    env = load_env(ROOT / ".env")
    db = MongoClient(env["MONGODB_URI"], serverSelectionTimeoutMS=20000)[
        env.get("MONGODB_DB") or "instascope"
    ]

    rows: list[dict[str, str | int | float]] = []
    for p in db["profiles"].find({}):
        created = p.get("created_at")
        if created and created.replace(tzinfo=timezone.utc) >= IMPORT_CUTOFF:
            continue
        s = p.get("student") or {}
        sid = re.sub(r"\s+", "", str(s.get("student_id") or "").strip().upper())
        if not sid:
            continue
        rows.append(
            {
                "student_id": sid,
                "instagram_username": p.get("username") or s.get("instagram_username") or "",
                "full_name": s.get("full_name") or p.get("full_name") or "",
                "email": s.get("email") or "",
                "mobile": s.get("mobile") or "",
                "university": s.get("university") or "",
                "followers": int(p.get("followers") or 0),
                "following": int(p.get("following") or 0),
                "posts_count": int(p.get("posts_count") or 0),
                "avg_likes": float(p.get("avg_likes") or 0),
                "avg_views": float(p.get("avg_views") or 0),
                "avg_comments": float(p.get("avg_comments") or 0),
                "engagement_rate": float(p.get("engagement_rate") or 0),
                "growth_pct_today": float(p.get("growth_pct_today") or 0),
                "is_private": bool(p.get("is_private")),
                "status": p.get("status") or "",
                "last_success_at": iso(p.get("last_success_at")),
                "last_scraped_at": iso(p.get("last_scraped_at")),
                "last_error": p.get("last_error") or "",
                "youtube_connected": bool(p.get("youtube_connected")),
                "profile_url": p.get("profile_url") or "",
            }
        )

    rows.sort(key=lambda r: (str(r["student_id"]), str(r["instagram_username"])))
    fieldnames = [
        "student_id",
        "instagram_username",
        "full_name",
        "email",
        "mobile",
        "university",
        "followers",
        "following",
        "posts_count",
        "avg_likes",
        "avg_views",
        "avg_comments",
        "engagement_rate",
        "growth_pct_today",
        "is_private",
        "status",
        "last_success_at",
        "last_scraped_at",
        "last_error",
        "youtube_connected",
        "profile_url",
    ]
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    scraped = sum(1 for r in rows if r["last_success_at"] or int(r["followers"] or 0) > 0 or int(r["posts_count"] or 0) > 0)
    print(f"Wrote {len(rows)} rows to {OUT_PATH} (with scrape signal: {scraped})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
