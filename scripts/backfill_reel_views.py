"""Backfill missing Instagram reel view counts for existing Mongo posts.

Usage:
  python scripts/backfill_reel_views.py nihaa.creates
  python scripts/backfill_reel_views.py nihaa.creates --limit 40

Only updates views/likes/comments upward (never wipes better numbers).
SPARK performance points recompute from posts on the next dashboard load.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scraper"))
sys.path.insert(0, str(ROOT / "packages" / "python-shared"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from instascope_shared.db.mongodb import close_db, connect_db
from instascope_shared.models import Post, Profile
from instascope_scraper.profile import ScrapedPost, _enrich_views_via_http
from instascope_scraper.proxy_pool import next_proxy
from instascope_scraper.types import proxy_to_httpx_url


def _as_scraped(post: Post) -> ScrapedPost:
    mt = getattr(post.media_type, "value", None) or str(post.media_type or "reel")
    posted = post.posted_at.isoformat() if post.posted_at else None
    return ScrapedPost(
        ig_post_id=str(post.ig_post_id or ""),
        shortcode=str(post.shortcode or ""),
        media_type=str(mt).lower(),
        caption=post.caption,
        thumbnail_url=post.thumbnail_url,
        permalink=post.permalink or (f"https://www.instagram.com/p/{post.shortcode}/" if post.shortcode else None),
        likes=int(post.likes or 0),
        comments=int(post.comments or 0),
        views=int(post.views or 0),
        posted_at=posted,
        is_video=str(mt).lower() in {"reel", "video", "clip", "igtv"},
    )


async def backfill(username: str, *, limit: int = 0, only_zero: bool = True) -> None:
    await connect_db()
    profile = await Profile.find_one(Profile.username == username.lstrip("@").strip().lower())
    if profile is None:
        # case-insensitive fallback
        profile = await Profile.find_one(
            {"username": {"$regex": f"^{username.lstrip('@').strip()}$", "$options": "i"}}
        )
    if profile is None:
        print(f"@{username}: profile not found")
        await close_db()
        return

    pid = str(profile.id)
    q: dict = {
        "profile_id": pid,
        "media_type": {"$in": ["reel", "video", "clip", "igtv", "REEL", "VIDEO"]},
    }
    if only_zero:
        q["$or"] = [{"views": 0}, {"views": None}, {"views": {"$exists": False}}]

    posts = await Post.find(q).sort(-Post.posted_at).to_list(limit if limit > 0 else None)
    print(f"@{profile.username}: enriching {len(posts)} reels (only_zero={only_zero})")
    if not posts:
        await close_db()
        return

    scraped = [_as_scraped(p) for p in posts]
    proxy = next_proxy()
    proxy_url = proxy_to_httpx_url(proxy) if proxy else None
    print(f"@{profile.username}: proxy={bool(proxy_url)}")

    enriched = await _enrich_views_via_http(
        scraped, username=profile.username, proxy_url=proxy_url
    )
    by_code = {p.shortcode: p for p in enriched}

    updated = 0
    gained_views = 0
    for post in posts:
        fresh = by_code.get(post.shortcode)
        if not fresh:
            continue
        new_views = max(int(post.views or 0), int(fresh.views or 0))
        new_likes = max(int(post.likes or 0), int(fresh.likes or 0))
        new_comments = max(int(post.comments or 0), int(fresh.comments or 0))
        if (
            new_views == int(post.views or 0)
            and new_likes == int(post.likes or 0)
            and new_comments == int(post.comments or 0)
        ):
            continue
        if new_views > int(post.views or 0):
            gained_views += 1
        post.views = new_views
        post.likes = new_likes
        post.comments = new_comments
        post.updated_at = datetime.utcnow()
        await post.save()
        updated += 1
        print(
            f"  {post.shortcode} views {fresh.views} likes {fresh.likes} comments {fresh.comments}"
        )

    print(
        f"@{profile.username}: done updated_rows={updated} newly_got_views={gained_views}/{len(posts)}"
    )
    await close_db()


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("usernames", nargs="+", help="Instagram usernames")
    parser.add_argument("--limit", type=int, default=0, help="Max reels per account (0=all)")
    parser.add_argument(
        "--all-reels",
        action="store_true",
        help="Re-check every reel, not only views==0",
    )
    args = parser.parse_args()
    for name in args.usernames:
        try:
            await backfill(name, limit=args.limit, only_zero=not args.all_reels)
        except Exception as exc:  # noqa: BLE001
            print(f"@{name}: FAIL {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
