"""Dump overall SPARK leaderboard top 50 from MongoDB (same path as admin board)."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

# Load .env from repo root
root = Path(__file__).resolve().parents[1]
env_path = root / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, str(root / "packages" / "python-shared"))

from instascope_shared.db.mongodb import connect_db, close_db
from instascope_shared.services.spark import build_leaderboard


async def main() -> None:
    await connect_db()
    try:
        rows = await build_leaderboard(sort="overall")
        top = rows[:50]
        out = []
        for r in top:
            bd = r.get("points_breakdown") or {}
            out.append(
                {
                    "rank": r.get("rank"),
                    "username": r.get("username"),
                    "name": r.get("name"),
                    "campus": r.get("campus"),
                    "tier": r.get("tier"),
                    "points": r.get("points"),
                    "consistency": bd.get("consistency"),
                    "performance": bd.get("performance"),
                    "growth": bd.get("growth"),
                    "collaborations": bd.get("collaborations"),
                    "revenue": bd.get("revenue"),
                    "recognition": bd.get("recognition"),
                    "participation": bd.get("participation"),
                    "monthly_bonuses": bd.get("monthly_bonuses"),
                    "bonus": bd.get("bonus"),
                    "followers": r.get("followers"),
                    "combined_audience": r.get("combined_audience"),
                    "youtube_subscribers": r.get("youtube_subscribers"),
                    "views": r.get("views"),
                    "engagement": r.get("engagement"),
                    "posts_count": r.get("posts_count"),
                    "window_from": r.get("window_from"),
                    "window_to": r.get("window_to"),
                }
            )
        print(json.dumps({"total_creators": len(rows), "top50": out}, indent=2, default=str))
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
