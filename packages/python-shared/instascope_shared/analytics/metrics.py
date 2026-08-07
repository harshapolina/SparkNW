"""Exact derived metrics from scraped profile + posts.

Every Insights card (except profile-level IG totals like posts_count /
highlight_reel_count) is computed ONLY from posts inside the SPARK programme
window: SPARK_COHORT_START (default 2026-07-15) → end of today (UTC).
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from instascope_shared.cohort import clamp_scoring_window, cohort_start_ymd
from instascope_shared.domain.instagram import engagement_rate, mean
from instascope_shared.instagram_time import infer_posted_at


_HASHTAG_RE = re.compile(r"#([A-Za-z0-9_]+)")
_MENTION_RE = re.compile(r"@([A-Za-z0-9._]+)")

_REEL_MEDIA = frozenset({"reel", "video", "clips", "graphvideo"})
_IMAGE_MEDIA = frozenset({"image", "graphimage"})
_CAROUSEL_MEDIA = frozenset({"carousel", "graphsidecar"})
_MIN_VIEWS = 10  # ignore noise / missing view payloads


def _media(p: dict[str, Any]) -> str:
    return str(p.get("media_type") or "").lower().strip()


def _nonneg_int(v: Any) -> int:
    """Parse to int ≥ 0. Never raises."""
    try:
        if v is None or v is False:
            return 0
        if isinstance(v, bool):
            return int(v)
        n = int(float(v)) if not isinstance(v, int) else v
        return n if n > 0 else 0
    except (TypeError, ValueError, OverflowError):
        return 0


def _naive_utc(dt: datetime) -> datetime:
    """Normalize any datetime to naive UTC for safe comparisons."""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _safe_div(num: float, den: float, *, default: float = 0.0) -> float:
    if den == 0 or den is None:
        return default
    try:
        return num / den
    except (ZeroDivisionError, TypeError, OverflowError):
        return default


def _is_reelish(p: dict[str, Any]) -> bool:
    if _media(p) in _REEL_MEDIA:
        return True
    return bool(p.get("is_video"))


def _empty_metrics(
    *,
    posts_stored: int,
    posts_missing_dates: int,
    programme_window: bool,
    window_start: datetime,
    window_end: datetime,
) -> dict[str, Any]:
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
        "avg_reel_views": 0.0,
        "total_reel_views": 0,
        "max_reel_views": 0,
        "reel_posts_with_views": 0,
        "posts_with_views": 0,
        "posts_without_views": 0,
        "avg_caption_length": 0.0,
        "comments_to_likes_ratio": 0.0,
        "video_share_pct": 0.0,
        "median_likes": 0.0,
        "max_likes": 0,
        "max_views": 0,
        "min_likes": 0,
        "window_from": window_start.strftime("%Y-%m-%d") if programme_window else None,
        "window_to": window_end.strftime("%Y-%m-%d") if programme_window else None,
        "cohort_start": cohort_start_ymd() if programme_window else None,
        "posts_stored": posts_stored,
        "posts_missing_dates": posts_missing_dates,
        "posts_in_window": 0,
    }


def parse_posted_at(raw: Any, post: dict[str, Any] | None = None) -> datetime | None:
    """Parse posted_at; if missing, derive from Instagram shortcode / media id."""
    if post is None:
        post = {"posted_at": raw}
    else:
        post = {**post, "posted_at": raw if raw is not None else post.get("posted_at")}
    try:
        return infer_posted_at(
            posted_at=post.get("posted_at"),
            shortcode=str(post.get("shortcode") or "") or None,
            ig_post_id=str(post.get("ig_post_id") or post.get("id") or "") or None,
        )
    except Exception:
        return None


def filter_posts_to_programme_window(
    posts: list[dict[str, Any]],
    *,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[dict[str, Any]]:
    """Keep only posts with posted_at inside the SPARK programme window.

    Posts with missing / unparseable dates are dropped (never invent a date).
    Resolved posted_at is attached so downstream metrics use one clock.
    """
    start, end = clamp_scoring_window(since, until)
    start_n = _naive_utc(start)
    end_n = _naive_utc(end)
    out: list[dict[str, Any]] = []
    for p in posts or []:
        if not isinstance(p, dict):
            continue
        dt = parse_posted_at(p.get("posted_at"), p)
        if dt is None:
            continue
        dt_n = _naive_utc(dt)
        if dt_n < start_n or dt_n > end_n:
            continue
        enriched = dict(p)
        enriched["posted_at"] = dt_n  # store naive UTC for consistent math
        out.append(enriched)
    return out


def compute_post_metrics(
    posts: list[dict[str, Any]],
    *,
    followers: int,
    programme_window: bool = True,
) -> dict[str, Any]:
    """Compute portfolio metrics.

    By default only posts dated on/after SPARK programme start (15 Jul 2026)
    through today (UTC) are included — never lifetime / pre-programme posts.

    Safe against: empty sets, missing dates, naive/aware tz mix, zero followers,
    zero likes, negative/garbage numeric fields, non-dict rows.
    """
    try:
        window_start, window_end = clamp_scoring_window()
    except Exception:
        # Absolute last resort so Insights never 500
        window_start = datetime(2026, 7, 15)
        window_end = datetime.utcnow().replace(hour=23, minute=59, second=59, microsecond=0)

    raw_posts = [p for p in (posts or []) if isinstance(p, dict)]
    posts_stored = len(raw_posts)
    posts_missing_dates = 0
    for p in raw_posts:
        if parse_posted_at(p.get("posted_at"), p) is None:
            posts_missing_dates += 1

    followers_n = _nonneg_int(followers)

    if programme_window:
        window_posts = filter_posts_to_programme_window(
            raw_posts, since=window_start, until=window_end
        )
    else:
        # Still normalize dates; undated rows stay out of time-based metrics
        window_posts = []
        for p in raw_posts:
            dt = parse_posted_at(p.get("posted_at"), p)
            enriched = dict(p)
            if dt is not None:
                enriched["posted_at"] = _naive_utc(dt)
            window_posts.append(enriched)

    if not window_posts:
        return _empty_metrics(
            posts_stored=posts_stored,
            posts_missing_dates=posts_missing_dates,
            programme_window=programme_window,
            window_start=window_start,
            window_end=window_end,
        )

    likes = [_nonneg_int(p.get("likes")) for p in window_posts]
    comments = [_nonneg_int(p.get("comments")) for p in window_posts]
    total_likes = sum(likes)
    total_comments = sum(comments)

    view_vals: list[int] = []
    for p in window_posts:
        v = _nonneg_int(p.get("views"))
        if v >= _MIN_VIEWS:
            view_vals.append(v)

    posts_with_views = sum(1 for p in window_posts if _nonneg_int(p.get("views")) >= _MIN_VIEWS)
    posts_without_views = len(window_posts) - posts_with_views

    reelish = [p for p in window_posts if _is_reelish(p)]
    reel_view_vals = [
        _nonneg_int(p.get("views")) for p in reelish if _nonneg_int(p.get("views")) >= _MIN_VIEWS
    ]
    avg_reel_views = float(round(mean(reel_view_vals))) if reel_view_vals else 0.0
    total_reel_views = sum(reel_view_vals)
    max_reel_views = max(reel_view_vals) if reel_view_vals else 0

    caps = [str(p.get("caption") or "") for p in window_posts]
    hashtags: list[str] = []
    mentions: list[str] = []
    for c in caps:
        hashtags.extend(h.lower() for h in _HASHTAG_RE.findall(c))
        mentions.extend(m.lower() for m in _MENTION_RE.findall(c))

    # Time-based metrics — always naive UTC, never mix tz
    now_n = _naive_utc(datetime.now(timezone.utc))
    last_7 = now_n - timedelta(days=7)
    last_30 = now_n - timedelta(days=30)
    # Never look back before the programme floor when windowing is on
    if programme_window:
        floor_n = _naive_utc(window_start)
        last_7 = max(last_7, floor_n)
        last_30 = max(last_30, floor_n)

    dated: list[datetime] = []
    for p in window_posts:
        raw_dt = p.get("posted_at")
        if isinstance(raw_dt, datetime):
            dated.append(_naive_utc(raw_dt))
        else:
            dt = parse_posted_at(raw_dt, p)
            if dt is not None:
                dated.append(_naive_utc(dt))

    posts_7 = sum(1 for d in dated if d >= last_7)
    posts_30 = sum(1 for d in dated if d >= last_30)

    # Posting / week: programme-anchored when possible
    #   weeks = max(days from window start (or first post) → last post, 1) / 7
    #   freq  = dated_posts / weeks
    if dated:
        if programme_window:
            start_ref = _naive_utc(window_start)
        else:
            start_ref = min(dated)
        end_ref = max(dated)
        span_days = max((end_ref - start_ref).days, 1)
        freq = round(_safe_div(float(len(dated)), span_days / 7.0), 2)
    else:
        freq = 0.0

    ranked = sorted(window_posts, key=lambda p: _nonneg_int(p.get("likes")), reverse=True)
    best = ranked[0] if ranked else None
    worst = ranked[-1] if ranked else None

    media_counts = Counter(_media(p) or "unknown" for p in window_posts)
    image_count = sum(media_counts.get(k, 0) for k in _IMAGE_MEDIA)
    video_count = media_counts.get("video", 0) + media_counts.get("graphvideo", 0)
    reel_count = media_counts.get("reel", 0) + media_counts.get("clips", 0)
    carousel_count = sum(media_counts.get(k, 0) for k in _CAROUSEL_MEDIA)

    avg_likes = mean(likes)
    avg_comments = mean(comments)
    avg_views = float(round(mean(view_vals))) if view_vals else 0.0

    video_share_n = video_count + reel_count
    video_share_pct = round(_safe_div(float(video_share_n), float(len(window_posts))) * 100, 1)

    sorted_likes = sorted(likes)
    median_likes = float(sorted_likes[len(sorted_likes) // 2]) if sorted_likes else 0.0

    last_post_at: str | None = None
    if dated:
        try:
            last_post_at = max(dated).replace(tzinfo=timezone.utc).isoformat()
        except Exception:
            last_post_at = max(dated).isoformat()

    return {
        "avg_likes": round(avg_likes, 2),
        "avg_comments": round(avg_comments, 2),
        "avg_views": avg_views,
        "engagement_rate": engagement_rate(
            avg_likes=avg_likes, avg_comments=avg_comments, followers=followers_n
        ),
        "like_follower_ratio": round(_safe_div(avg_likes, float(followers_n)) * 100, 4),
        "comment_follower_ratio": round(_safe_div(avg_comments, float(followers_n)) * 100, 4),
        "sampled_posts": len(window_posts),
        "image_count": image_count,
        "video_count": video_count,
        "reel_count": reel_count,
        "carousel_count": carousel_count,
        "posts_last_7d": posts_7,
        "posts_last_30d": posts_30,
        "posting_frequency_per_week": freq,
        "best_post_shortcode": (best or {}).get("shortcode"),
        "best_post_likes": _nonneg_int((best or {}).get("likes")),
        "worst_post_shortcode": (worst or {}).get("shortcode"),
        "worst_post_likes": _nonneg_int((worst or {}).get("likes")),
        "last_post_at": last_post_at,
        "top_hashtags": [h for h, _ in Counter(hashtags).most_common(8)],
        "top_mentions": [m for m, _ in Counter(mentions).most_common(5)],
        "total_likes_sampled": total_likes,
        "total_comments_sampled": total_comments,
        "total_views_sampled": sum(view_vals),
        "avg_reel_views": avg_reel_views,
        "total_reel_views": total_reel_views,
        "max_reel_views": max_reel_views,
        "reel_posts_with_views": len(reel_view_vals),
        "posts_with_views": posts_with_views,
        "posts_without_views": posts_without_views,
        "avg_caption_length": round(mean([len(c) for c in caps]), 1) if caps else 0.0,
        "comments_to_likes_ratio": round(
            _safe_div(float(total_comments), float(total_likes)) * 100, 2
        ),
        "video_share_pct": video_share_pct,
        "median_likes": median_likes,
        "max_likes": max(likes) if likes else 0,
        "max_views": max_reel_views or (max(view_vals) if view_vals else 0),
        "min_likes": min(likes) if likes else 0,
        "window_from": window_start.strftime("%Y-%m-%d") if programme_window else None,
        "window_to": window_end.strftime("%Y-%m-%d") if programme_window else None,
        "cohort_start": cohort_start_ymd() if programme_window else None,
        "posts_stored": posts_stored,
        "posts_missing_dates": posts_missing_dates,
        "posts_in_window": len(window_posts),
    }
