#!/usr/bin/env python3
"""Scrape one Instagram username locally and upsert results into MongoDB Atlas via pymongo.

Use when the cloud API host IP is blocked by Instagram but a local network can scrape.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "python-shared"))
sys.path.insert(0, str(ROOT / "scraper"))

from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId

load_dotenv(ROOT / ".env")


def load_env_file(path: Path) -> dict[str, str]:
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


async def scrape(username: str, timeout: int):
    os.environ.setdefault("SCRAPE_BROWSER_ON_PARTIAL", "0")
    os.environ.setdefault("SCRAPE_MAX_RETRIES", "1")
    os.environ.setdefault("SCRAPE_ENRICH_MAX", "8")
    from instascope_scraper.profile import scrape_profile

    return await asyncio.wait_for(
        scrape_profile(username, headless=True, live=True),
        timeout=timeout,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("username", help="Instagram username without @")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--profile-id", default="", help="Optional Mongo profile ObjectId")
    args = parser.parse_args()
    username = args.username.lstrip("@").strip()

    env = load_env_file(ROOT / ".env")
    uri = os.environ.get("MONGODB_URI") or env.get("MONGODB_URI")
    db_name = os.environ.get("MONGODB_DB") or env.get("MONGODB_DB") or "instascope"
    if not uri:
        print("MONGODB_URI missing", file=sys.stderr)
        return 1

    print(f"scraping @{username} locally…")
    result = asyncio.run(scrape(username, args.timeout))
    posts = [p.__dict__ if hasattr(p, "__dict__") else p for p in result.posts]
    # ScrapedPost may be a dataclass — prefer to_dict if present
    if result.posts and hasattr(result.posts[0], "to_dict"):
        posts = [p.to_dict() for p in result.posts]
    elif result.posts and hasattr(result, "to_dict"):
        full = result.to_dict()
        posts = full.get("posts") or posts

    payload = result.to_dict() if hasattr(result, "to_dict") else {
        "username": result.username,
        "followers": result.followers,
        "following": result.following,
        "posts_count": result.posts_count,
        "posts": posts,
        "full_name": result.full_name,
        "bio": result.bio,
        "website": result.website,
        "avatar_url": result.avatar_url,
        "is_verified": result.is_verified,
        "ig_user_id": result.ig_user_id,
        "is_private": getattr(result, "is_private", False),
        "is_business": getattr(result, "is_business", False),
        "category": getattr(result, "category", None),
        "highlight_reel_count": getattr(result, "highlight_reel_count", 0),
        "raw": result.raw,
    }
    print(
        f"scraped fol={payload.get('followers')} posts_count={payload.get('posts_count')} "
        f"got={len(payload.get('posts') or [])} path={(payload.get('raw') or {}).get('path')}"
    )

    client = MongoClient(uri, serverSelectionTimeoutMS=15000)
    db = client[db_name]
    query: dict = {"username": username}
    if args.profile_id:
        query = {"_id": ObjectId(args.profile_id)}
    profile = db.profiles.find_one(query)
    if not profile and not args.profile_id:
        # Prefer the profile that was just failing in admin UI
        profile = db.profiles.find_one({"username": username, "status": "failed"}) or db.profiles.find_one(
            {"username": username}
        )
    if not profile:
        print(f"PROFILE NOT FOUND: @{username}", file=sys.stderr)
        return 1

    now = datetime.now(timezone.utc)
    posts_data = payload.get("posts") or []
    followers = int(payload.get("followers") or 0)
    following = int(payload.get("following") or 0)
    posts_count = int(payload.get("posts_count") or len(posts_data) or 0)

    # Basic engagement averages
    likes = [int(p.get("likes") or 0) for p in posts_data]
    comments = [int(p.get("comments") or 0) for p in posts_data]
    views = [int(p.get("views") or 0) for p in posts_data]
    n = max(len(posts_data), 1)
    avg_likes = sum(likes) / n if posts_data else 0.0
    avg_comments = sum(comments) / n if posts_data else 0.0
    avg_views = sum(views) / n if posts_data else 0.0
    eng = ((avg_likes + avg_comments) / followers * 100.0) if followers else 0.0

    update = {
        "full_name": payload.get("full_name") or profile.get("full_name"),
        "bio": payload.get("bio") or profile.get("bio"),
        "website": payload.get("website") or profile.get("website"),
        "avatar_url": payload.get("avatar_url") or profile.get("avatar_url"),
        "is_verified": bool(payload.get("is_verified", profile.get("is_verified"))),
        "ig_user_id": payload.get("ig_user_id") or profile.get("ig_user_id"),
        "is_private": bool(payload.get("is_private", False)),
        "is_business": bool(payload.get("is_business", False)),
        "category": payload.get("category") or profile.get("category"),
        "highlight_reel_count": int(payload.get("highlight_reel_count") or 0),
        "followers": followers,
        "following": following,
        "posts_count": posts_count,
        "avg_likes": avg_likes,
        "avg_views": avg_views,
        "avg_comments": avg_comments,
        "engagement_rate": eng,
        "follower_following_ratio": round(followers / following, 4) if following else float(followers),
        "insights": {
            "avg_likes": avg_likes,
            "avg_comments": avg_comments,
            "avg_views": avg_views,
            "engagement_rate": eng,
            "sampled_posts": len(posts_data),
            "total_likes_sampled": sum(likes),
            "total_comments_sampled": sum(comments),
            "total_views_sampled": sum(views),
        },
        "status": "active",
        "last_error": None,
        "last_scraped_at": now,
        "last_success_at": now,
        "scrape_progress": {
            "active": False,
            "phase": "done",
            "scraped_posts": len(posts_data),
            "total_posts": posts_count,
            "posts_left": max(0, posts_count - len(posts_data)),
            "percent": 100 if posts_count == 0 else min(100, int(round(100 * len(posts_data) / posts_count))),
            "updated_at": now.isoformat().replace("+00:00", "Z"),
        },
        "updated_at": now,
    }
    db.profiles.update_one({"_id": profile["_id"]}, {"$set": update})

    # Replace stored posts for this profile
    pid = str(profile["_id"])
    db.posts.delete_many({"profile_id": pid})
    if posts_data:
        docs = []
        for p in posts_data:
            docs.append(
                {
                    "profile_id": pid,
                    "user_id": profile.get("user_id"),
                    "ig_post_id": p.get("ig_post_id") or p.get("id"),
                    "shortcode": p.get("shortcode"),
                    "media_type": p.get("media_type") or "unknown",
                    "caption": p.get("caption"),
                    "permalink": p.get("permalink")
                    or (f"https://www.instagram.com/p/{p.get('shortcode')}/" if p.get("shortcode") else None),
                    "thumbnail_url": p.get("thumbnail_url") or p.get("display_url"),
                    "likes": int(p.get("likes") or 0),
                    "comments": int(p.get("comments") or 0),
                    "views": int(p.get("views") or 0),
                    "posted_at": p.get("posted_at"),
                    "created_at": now,
                    "updated_at": now,
                }
            )
        db.posts.insert_many(docs)

    print(
        f"SAVED profile_id={pid} status=active fol={followers} "
        f"posts_count={posts_count} saved_posts={len(posts_data)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
