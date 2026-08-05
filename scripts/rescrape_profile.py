"""Re-scrape usernames and write full results to MongoDB via pymongo (no Beanie)."""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scraper"))
sys.path.insert(0, str(ROOT / "packages" / "python-shared"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from pymongo import MongoClient

from instascope_scraper.profile import scrape_profile
from instascope_shared.analytics.metrics import compute_post_metrics


def _db():
    uri = os.getenv("MONGODB_URI")
    name = os.getenv("MONGODB_DB", "instascope")
    if not uri:
        raise SystemExit("MONGODB_URI missing in .env")
    return MongoClient(uri)[name]


async def rescrape(username: str) -> None:
    uname = username.lstrip("@").strip().lower()
    db = _db()
    profile = db.profiles.find_one({"username": {"$regex": f"^{uname}$", "$options": "i"}})
    if not profile:
        print(f"@{uname}: not found in DB")
        return

    pid = str(profile["_id"])
    print(f"@{profile.get('username')}: scraping… (was sampled={((profile.get('insights') or {}).get('sampled_posts'))})")

    result = await scrape_profile(profile["username"], headless=True, proxy=None, delay_seconds=1.0, live=True)
    data = result.to_dict()
    posts = data.get("posts") or []
    followers = int(data.get("followers") or 0)
    following = int(data.get("following") or 0)
    posts_count = int(data.get("posts_count") or 0)

    if posts_count > 0 and len(posts) < (posts_count if posts_count <= 12 else max(posts_count - 2, 1)):
        print(f"@{uname}: incomplete {len(posts)}/{posts_count} — not saving")
        return

    metrics = compute_post_metrics(posts, followers=followers)
    now = datetime.now(timezone.utc)

    db.profiles.update_one(
        {"_id": profile["_id"]},
        {
            "$set": {
                "full_name": data.get("full_name") or profile.get("full_name"),
                "bio": data.get("bio") or profile.get("bio"),
                "website": data.get("website") or profile.get("website"),
                "avatar_url": data.get("avatar_url") or profile.get("avatar_url"),
                "ig_user_id": data.get("ig_user_id") or profile.get("ig_user_id"),
                "is_private": bool(data.get("is_private", False)),
                "followers": followers,
                "following": following,
                "posts_count": posts_count,
                "avg_likes": float(metrics["avg_likes"]),
                "avg_views": float(metrics["avg_views"]),
                "avg_comments": float(metrics["avg_comments"]),
                "engagement_rate": float(metrics["engagement_rate"]),
                "follower_following_ratio": round(followers / following, 4) if following else float(followers),
                "insights": metrics,
                "status": "active",
                "last_error": None,
                "last_scraped_at": now,
                "last_success_at": now,
                "updated_at": now,
            }
        },
    )

    # Posts may store profile_id as str or ObjectId depending on writer
    from bson import ObjectId

    del_q: list[dict] = [{"profile_id": pid}]
    try:
        del_q.append({"profile_id": ObjectId(pid)})
    except Exception:
        pass
    db.posts.delete_many({"$or": del_q})
    saved = 0
    for p in posts:
        ig_post_id = str(p.get("ig_post_id") or p.get("id") or "")
        if not ig_post_id:
            continue
        posted_at = p.get("posted_at")
        if isinstance(posted_at, str):
            try:
                posted_at = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
            except ValueError:
                posted_at = None
        doc = {
            "profile_id": pid,
            "user_id": profile.get("user_id"),
            "ig_post_id": ig_post_id,
            "shortcode": str(p.get("shortcode") or ig_post_id),
            "media_type": p.get("media_type") or "image",
            "caption": p.get("caption"),
            "thumbnail_url": p.get("thumbnail_url"),
            "permalink": p.get("permalink") or f"https://instagram.com/p/{p.get('shortcode')}/",
            "likes": int(p.get("likes") or 0),
            "comments": int(p.get("comments") or 0),
            "views": int(p.get("views") or 0),
            "posted_at": posted_at,
            "scraped_at": now,
            "updated_at": now,
        }
        db.posts.update_one({"ig_post_id": ig_post_id}, {"$set": doc}, upsert=True)
        saved += 1

    path = (data.get("raw") or {}).get("path") if isinstance(data.get("raw"), dict) else None
    print(
        f"@{profile.get('username')}: OK scraped={len(posts)}/{posts_count} "
        f"saved={saved} sampled={metrics.get('sampled_posts')} path={path} status=active"
    )


async def main() -> None:
    names = [a for a in sys.argv[1:] if a.strip()]
    if not names:
        print("usage: python scripts/rescrape_profile.py <username> ...")
        return
    for name in names:
        try:
            await rescrape(name)
        except Exception as exc:  # noqa: BLE001
            print(f"@{name}: FAIL {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
