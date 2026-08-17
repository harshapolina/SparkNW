"""Recompute exact avg_* + insights from stored posts (no Instagram re-scrape)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Allow running from repo root or inside the API container
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "python-shared"))

from instascope_shared.analytics.metrics import compute_post_metrics
from instascope_shared.db.mongodb import close_db, connect_db
from instascope_shared.models import Post, Profile


async def main() -> None:
    await connect_db()
    try:
        profiles = await Profile.find_all().to_list()
        updated = 0
        for profile in profiles:
            posts = await Post.find(Post.profile_id == str(profile.id)).to_list()
            posts_data = []
            for p in posts:
                media = p.media_type.value if hasattr(p.media_type, "value") else str(p.media_type)
                media_l = str(media or "").lower()
                posts_data.append(
                    {
                        "shortcode": p.shortcode,
                        "ig_post_id": getattr(p, "ig_post_id", None),
                        "id": getattr(p, "ig_post_id", None),
                        "media_type": media,
                        "is_video": media_l in {"reel", "video", "clips", "graphvideo"},
                        "caption": p.caption,
                        "likes": p.likes,
                        "comments": p.comments,
                        "views": p.views,
                        "posted_at": p.posted_at.isoformat() if p.posted_at else None,
                    }
                )
            metrics = compute_post_metrics(
                posts_data, followers=int(profile.followers or 0), programme_window=True
            )
            profile.avg_likes = float(metrics["avg_likes"])
            profile.avg_views = float(metrics["avg_views"])
            profile.avg_comments = float(metrics["avg_comments"])
            profile.engagement_rate = float(metrics["engagement_rate"])
            profile.follower_following_ratio = (
                round(profile.followers / profile.following, 4)
                if profile.following
                else float(profile.followers)
            )
            from instascope_shared.services.spark_points import merge_spark_scoring_insights

            prev_insights = profile.insights if isinstance(profile.insights, dict) else {}
            profile.insights = merge_spark_scoring_insights(prev_insights, metrics)
            await profile.save()
            updated += 1
            print(
                f"updated @{profile.username}: avg_likes={profile.avg_likes} "
                f"avg_views={profile.avg_views} sampled={metrics['sampled_posts']}"
            )
        print(f"done: {updated} profiles")
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
