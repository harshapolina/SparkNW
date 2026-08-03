"""Exact derived metrics from scraped profile + posts."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from instascope_shared.domain.instagram import engagement_rate, mean


_HASHTAG_RE = re.compile(r"#([A-Za-z0-9_]+)")
_MENTION_RE = re.compile(r"@([A-Za-z0-9._]+)")


def _media(p: dict[str, Any]) -> str:
    return str(p.get("media_type") or "").lower()


def _int(v: Any) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def compute_post_metrics(posts: list[dict[str, Any]], *, followers: int) -> dict[str, Any]:
    """Compute exact portfolio metrics from the scraped post set only."""
    if not posts:
        return {
            "avg_likes": 0.0,
            "avg_comments": 0.0,
            "avg_views": 0.0,
            "engagement_rate": 0.0,
            "like_follower_ratio": 0.0,
            "comment_follower_ratio": 0.0,
            "sampled_posts": 0,
            "image_count": 0,
            "video_count": 0,
            "reel_count": 0,
            "carousel_count": 0,
            "posts_last_7d": 0,
            "posts_last_30d": 0,
            "posting_frequency_per_week": 0.0,
            "best_post_shortcode": None,
            "best_post_likes": 0,
            "worst_post_shortcode": None,
            "worst_post_likes": 0,
            "last_post_at": None,
            "top_hashtags": [],
            "top_mentions": [],
            "total_likes_sampled": 0,
            "total_comments_sampled": 0,
            "total_views_sampled": 0,
            "posts_with_views": 0,
            "posts_without_views": 0,
            "avg_caption_length": 0.0,
            "comments_to_likes_ratio": 0.0,
            "video_share_pct": 0.0,
            "median_likes": 0.0,
            "max_likes": 0,
            "max_views": 0,
            "min_likes": 0,
        }

    likes = [_int(p.get("likes")) for p in posts]
    comments = [_int(p.get("comments")) for p in posts]

    view_vals: list[int] = []
    for p in posts:
        v = _int(p.get("views"))
        if v >= 10:
            view_vals.append(v)

    posts_with_views = sum(1 for p in posts if _int(p.get("views")) >= 10)
    posts_without_views = len(posts) - posts_with_views

    caps = [str(p.get("caption") or "") for p in posts]
    hashtags: list[str] = []
    mentions: list[str] = []
    for c in caps:
        hashtags.extend(h.lower() for h in _HASHTAG_RE.findall(c))
        mentions.extend(m.lower() for m in _MENTION_RE.findall(c))

    now = datetime.now(timezone.utc)
    last_7 = now - timedelta(days=7)
    last_30 = now - timedelta(days=30)
    dated: list[datetime] = []
    for p in posts:
        raw = p.get("posted_at")
        if not raw:
            continue
        if isinstance(raw, datetime):
            dt = raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
        else:
            try:
                dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            except ValueError:
                continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dated.append(dt.astimezone(timezone.utc))

    posts_7 = sum(1 for d in dated if d >= last_7)
    posts_30 = sum(1 for d in dated if d >= last_30)
    if len(dated) >= 2:
        span_days = max((max(dated) - min(dated)).days, 1)
        freq = round(len(dated) / (span_days / 7), 2)
    else:
        freq = float(len(dated))

    # Best / worst by likes among sampled posts
    ranked = sorted(posts, key=lambda p: _int(p.get("likes")), reverse=True)
    best = ranked[0] if ranked else None
    worst = ranked[-1] if ranked else None

    media_counts = Counter(_media(p) or "unknown" for p in posts)
    avg_likes = mean(likes)
    avg_comments = mean(comments)
    avg_views = float(round(mean(view_vals))) if view_vals else 0.0

    return {
        "avg_likes": round(avg_likes, 2),
        "avg_comments": round(avg_comments, 2),
        "avg_views": avg_views,
        "engagement_rate": engagement_rate(
            avg_likes=avg_likes, avg_comments=avg_comments, followers=followers
        ),
        "like_follower_ratio": round((avg_likes / followers) * 100, 4) if followers else 0.0,
        "comment_follower_ratio": round((avg_comments / followers) * 100, 4) if followers else 0.0,
        "sampled_posts": len(posts),
        "image_count": media_counts.get("image", 0) + media_counts.get("graphimage", 0),
        "video_count": media_counts.get("video", 0) + media_counts.get("graphvideo", 0),
        "reel_count": media_counts.get("reel", 0) + media_counts.get("clips", 0),
        "carousel_count": media_counts.get("carousel", 0) + media_counts.get("graphsidecar", 0),
        "posts_last_7d": posts_7,
        "posts_last_30d": posts_30,
        "posting_frequency_per_week": freq,
        "best_post_shortcode": (best or {}).get("shortcode"),
        "best_post_likes": _int((best or {}).get("likes")),
        "worst_post_shortcode": (worst or {}).get("shortcode"),
        "worst_post_likes": _int((worst or {}).get("likes")),
        "last_post_at": max(dated).isoformat() if dated else None,
        "top_hashtags": [h for h, _ in Counter(hashtags).most_common(8)],
        "top_mentions": [m for m, _ in Counter(mentions).most_common(5)],
        "total_likes_sampled": sum(likes),
        "total_comments_sampled": sum(comments),
        "total_views_sampled": sum(view_vals),
        "posts_with_views": posts_with_views,
        "posts_without_views": posts_without_views,
        "avg_caption_length": round(mean([len(c) for c in caps]), 1) if caps else 0.0,
        "comments_to_likes_ratio": round((sum(comments) / sum(likes)) * 100, 2) if sum(likes) else 0.0,
        "video_share_pct": round(
            (
                (
                    media_counts.get("video", 0)
                    + media_counts.get("graphvideo", 0)
                    + media_counts.get("reel", 0)
                    + media_counts.get("clips", 0)
                )
                / len(posts)
            )
            * 100,
            1,
        ),
        "median_likes": float(sorted(likes)[len(likes) // 2]) if likes else 0.0,
        "max_likes": max(likes) if likes else 0,
        "max_views": max(view_vals) if view_vals else 0,
        "min_likes": min(likes) if likes else 0,
    }
