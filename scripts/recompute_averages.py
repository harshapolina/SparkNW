"""Recompute profile avg_likes / avg_views / avg_comments from stored posts."""

from __future__ import annotations

import asyncio

from instascope_shared.db.mongodb import close_db, connect_db
from instascope_shared.domain.instagram import engagement_rate, mean
from instascope_shared.models import Post, Profile


def _avg_views(posts: list[Post]) -> float:
    vals: list[int] = []
    for p in posts:
        v = int(p.views or 0)
        media = str(p.media_type.value if hasattr(p.media_type, "value") else p.media_type).lower()
        is_video = media in {"video", "reel", "graphvideo", "clips"}
        if v >= 10 and (is_video or True):
            # Prefer video/reel, but still accept high view counts on unknown types
            if is_video or v >= 10:
                vals.append(v)
    # Deduplicate: keep only meaningful view counts
    vals = [v for v in vals if v >= 10]
    return float(round(mean(vals))) if vals else 0.0


async def main() -> None:
    await connect_db()
    try:
        profiles = await Profile.find_all().to_list()
        for profile in profiles:
            posts = await Post.find(Post.profile_id == str(profile.id)).to_list()
            likes = [int(p.likes or 0) for p in posts]
            comments = [int(p.comments or 0) for p in posts]
            profile.avg_likes = mean(likes)
            profile.avg_comments = mean(comments)
            profile.avg_views = _avg_views(posts)
            profile.engagement_rate = engagement_rate(
                avg_likes=profile.avg_likes,
                avg_comments=profile.avg_comments,
                followers=profile.followers,
            )
            await profile.save()
            print(
                f"@{profile.username}: avg_views={profile.avg_views} "
                f"avg_likes={profile.avg_likes} posts={len(posts)}"
            )
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
