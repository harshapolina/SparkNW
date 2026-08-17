"""SPARK point calculator — overall leaderboard source of truth.

Design (see programme brief §5):
  Points reward consistency as a floor, performance as the multiplier, and
  breakthrough moments (growth / judged categories) as differentiators.

  total = consistency + min(performance, 3000) + growth
        + collaborations + revenue + recognition + participation + monthly_bonuses
        + legacy spark_bonus_points

Instagram + YouTube content and combined audience are scored together.
Crossposted Reels ↔ Shorts on the same calendar day count once (max views).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal, Sequence

from instascope_shared.cohort import clamp_scoring_window
from instascope_shared.models import Post, Profile, ProfileStatus, YouTubeVideo

# --- Category 3: Audience growth ---
COMBINED_GROWTH_MILESTONES = [
    (1_000, 25),
    (5_000, 75),
    (10_000, 150),
    (20_000, 300),
    (30_000, 500),
]
SINGLE_PLATFORM_50K_PTS = 1_000
GROWTH_MAX_WITHOUT_50K = 1_050

# Back-compat for callers that still import a flat list
GROWTH_MILESTONES = [
    *COMBINED_GROWTH_MILESTONES,
    (50_000, SINGLE_PLATFORM_50K_PTS),
]

SHORT_BANDS = [
    (100_000, 60),
    (50_000, 30),
    (10_000, 15),
    (1_000, 5),
]

LONG_BANDS = [
    (10_000, 50),
    (2_000, 25),
    (500, 10),
]

PERFORMANCE_CAP = 3_000
CONSISTENCY_PTS_PER_WEEK = 10
CONSISTENCY_CAP = 660
SHORT_MAX_SECONDS = 90
LONG_MIN_SECONDS = 180  # ≥3 min

CATEGORY_CAPS = {
    "collaborations": 850,
    "revenue": 3_000,
    "recognition": 500,
    "participation": 470,
    "monthly_bonuses": 1_350,
}

# Admin-awarded SPARK fields stored on Profile.insights — must survive scrapes.
SPARK_SCORING_INSIGHT_KEYS = (
    "spark_bonus_points",
    "spark_bonus_log",
    "spark_points",
    "spark_collaborations",
    "spark_revenue",
    "spark_recognition",
    "spark_participation",
    "spark_monthly_bonuses",
)


def merge_spark_scoring_insights(existing: dict[str, Any] | None, metrics: dict[str, Any] | None) -> dict[str, Any]:
    """Keep admin-awarded SPARK points when scrape/recompute overwrites insights."""
    out = dict(metrics or {})
    prev = existing if isinstance(existing, dict) else {}
    for key in SPARK_SCORING_INSIGHT_KEYS:
        if key in prev and key not in out:
            out[key] = prev[key]
    return out

PieceKind = Literal["short", "long", "other"]


@dataclass(frozen=True)
class ContentPiece:
    piece_id: str
    platform: str  # ig | yt | both
    kind: PieceKind
    views: int
    published_at: datetime
    label: str


def _naive_dt(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=None) if value.tzinfo else value


def _tier(points: int) -> str:
    if points >= 2500:
        return "GOLD"
    if points >= 1500:
        return "SILVER"
    return "BRONZE"


def _points_to_next(points: int) -> tuple[str | None, int]:
    if points < 500:
        return "BRONZE", 500 - points
    if points < 1500:
        return "SILVER", 1500 - points
    if points < 2500:
        return "GOLD", 2500 - points
    return None, 0


def _growth_pts_combined_absolute(followers: int) -> int:
    return sum(pts for need, pts in COMBINED_GROWTH_MILESTONES if followers >= need)


def growth_pts_absolute(followers: int) -> int:
    """All milestones including 50k on one absolute count (legacy helper)."""
    return sum(pts for need, pts in GROWTH_MILESTONES if followers >= need)


def growth_points_for_window(
    *,
    end_ig: int,
    end_yt: int = 0,
    start_ig: int = 0,
    start_yt: int = 0,
) -> int:
    """Milestones crossed inside the window.

    1k–30k use combined IG + YouTube. 50k requires a single platform.
    """
    end_ig = max(0, int(end_ig or 0))
    end_yt = max(0, int(end_yt or 0))
    start_ig = max(0, int(start_ig or 0))
    start_yt = max(0, int(start_yt or 0))

    pts = max(
        0,
        _growth_pts_combined_absolute(end_ig + end_yt)
        - _growth_pts_combined_absolute(start_ig + start_yt),
    )
    crossed_50k = (end_ig >= 50_000 and start_ig < 50_000) or (
        end_yt >= 50_000 and start_yt < 50_000
    )
    if crossed_50k:
        pts += SINGLE_PLATFORM_50K_PTS
    return pts


def short_form_points(views: int) -> int:
    for minimum, pts in SHORT_BANDS:
        if views >= minimum:
            return pts
    return 0


def long_form_points(views: int) -> int:
    for minimum, pts in LONG_BANDS:
        if views >= minimum:
            return pts
    return 0


def _is_long_form_ig(media_type: str, caption: str | None) -> bool:
    mt = (media_type or "").lower()
    if mt == "carousel":
        return True
    # Legacy: long caption on video treated as long when duration unknown
    if mt in {"video", "reel", "clip"} and caption and len(caption) > 280:
        return True
    return False


def _ig_piece_kind(media_type: str, caption: str | None) -> PieceKind:
    mt = (media_type or "").lower()
    if mt == "carousel" or _is_long_form_ig(mt, caption):
        return "long"
    if mt in {"video", "reel", "clip", "igtv"}:
        return "short"
    if mt in {"image", "photo", "unknown", ""}:
        return "other"
    return "short"


def _yt_piece_kind(*, is_short: bool, duration_seconds: int | None) -> PieceKind:
    if duration_seconds is None:
        return "short" if is_short else "long"
    if duration_seconds <= SHORT_MAX_SECONDS or is_short:
        return "short"
    if duration_seconds >= LONG_MIN_SECONDS:
        return "long"
    return "other"


def piece_from_ig(post: Post) -> ContentPiece | None:
    posted = _naive_dt(post.posted_at)
    if posted is None:
        return None
    mt = str(post.media_type.value if hasattr(post.media_type, "value") else post.media_type)
    kind = _ig_piece_kind(mt, post.caption)
    return ContentPiece(
        piece_id=f"ig:{getattr(post, 'shortcode', None) or getattr(post, 'ig_post_id', None) or id(post)}",
        platform="ig",
        kind=kind,
        views=int(post.views or 0),
        published_at=posted,
        label=f"IG {mt}",
    )


def piece_from_yt(video: YouTubeVideo) -> ContentPiece | None:
    posted = _naive_dt(getattr(video, "published_at", None))
    if posted is None:
        return None
    kind = _yt_piece_kind(
        is_short=bool(getattr(video, "is_short", False)),
        duration_seconds=getattr(video, "duration_seconds", None),
    )
    return ContentPiece(
        piece_id=f"yt:{getattr(video, 'video_id', id(video))}",
        platform="yt",
        kind=kind,
        views=int(getattr(video, "view_count", 0) or 0),
        published_at=posted,
        label="YT Short" if kind == "short" else ("YT Long" if kind == "long" else "YT"),
    )


def dedupe_crossposted_shorts(pieces: Sequence[ContentPiece]) -> list[ContentPiece]:
    """Same-day IG short + YT short → one piece (max views)."""
    shorts = [p for p in pieces if p.kind == "short"]
    rest = [p for p in pieces if p.kind != "short"]
    by_day: dict[str, list[ContentPiece]] = defaultdict(list)
    for p in shorts:
        by_day[p.published_at.strftime("%Y-%m-%d")].append(p)

    out: list[ContentPiece] = []
    for day, group in by_day.items():
        ig = sorted([p for p in group if p.platform == "ig"], key=lambda p: -p.views)
        yt = sorted([p for p in group if p.platform == "yt"], key=lambda p: -p.views)
        if ig and yt:
            n = min(len(ig), len(yt))
            for i in range(n):
                out.append(
                    ContentPiece(
                        piece_id=f"both:{day}:{i}",
                        platform="both",
                        kind="short",
                        views=max(ig[i].views, yt[i].views),
                        published_at=ig[i].published_at,
                        label="Crosspost short",
                    )
                )
            out.extend(ig[n:])
            out.extend(yt[n:])
        else:
            out.extend(group)
    return out + list(rest)


def performance_pts_for_piece(piece: ContentPiece) -> int:
    if piece.kind == "long":
        return long_form_points(piece.views)
    return short_form_points(piece.views)


def post_performance_pts(post: Post) -> tuple[int, bool, str]:
    mt = str(post.media_type.value if hasattr(post.media_type, "value") else post.media_type)
    piece = piece_from_ig(post)
    if piece is None:
        return 0, False, mt
    return performance_pts_for_piece(piece), piece.kind == "long", mt


def manual_category_points(insights: dict[str, Any] | None) -> dict[str, int]:
    insights = dict(insights or {})
    nested = insights.get("spark_points") if isinstance(insights.get("spark_points"), dict) else {}
    out: dict[str, int] = {}
    for key, cap in CATEGORY_CAPS.items():
        raw = nested.get(key) if isinstance(nested, dict) else None
        if raw is None:
            raw = insights.get(f"spark_{key}")
        try:
            val = int(raw or 0)
        except (TypeError, ValueError):
            val = 0
        out[key] = max(0, min(cap, val))
    try:
        legacy = int(insights.get("spark_bonus_points") or 0)
    except (TypeError, ValueError):
        legacy = 0
    out["bonus"] = max(0, legacy)
    return out


def collect_pieces(
    posts: Sequence[Post],
    videos: Sequence[YouTubeVideo] | None,
    *,
    window_start: datetime,
    window_end: datetime,
    include_youtube: bool,
) -> list[ContentPiece]:
    start = _naive_dt(window_start) or window_start
    end = _naive_dt(window_end) or window_end
    raw: list[ContentPiece] = []
    for post in posts:
        piece = piece_from_ig(post)
        if piece is None or piece.published_at < start or piece.published_at > end:
            continue
        raw.append(piece)
    if include_youtube and videos:
        for video in videos:
            piece = piece_from_yt(video)
            if piece is None or piece.published_at < start or piece.published_at > end:
                continue
            raw.append(piece)
    return dedupe_crossposted_shorts(raw)


def consistency_from_pieces(
    pieces: Sequence[ContentPiece],
    *,
    as_of: datetime,
) -> tuple[int, list[dict[str, Any]], int, int, int]:
    """10 pts/week for ≥2 shorts + ≥1 long-form, summed across programme weeks."""
    by_week: dict[tuple[int, int], dict[str, int]] = defaultdict(
        lambda: {"shorts": 0, "longs": 0}
    )
    for p in pieces:
        iso = p.published_at.isocalendar()
        wk = (int(iso[0]), int(iso[1]))
        if p.kind == "short":
            by_week[wk]["shorts"] += 1
        elif p.kind == "long":
            by_week[wk]["longs"] += 1

    history: list[dict[str, Any]] = []
    total = 0
    for (year, week), counts in sorted(by_week.items()):
        if counts["shorts"] >= 2 and counts["longs"] >= 1:
            total += CONSISTENCY_PTS_PER_WEEK
            history.append(
                {
                    "id": f"cons-{year}-W{week}",
                    "week": week,
                    "title": f"Weekly minimum — 2 shorts + 1 long-form (W{week})",
                    "category": "Consistency",
                    "points": CONSISTENCY_PTS_PER_WEEK,
                    "status": "approved",
                    "date": as_of.strftime("%Y-%m-%d"),
                }
            )
    total = min(total, CONSISTENCY_CAP)

    week_ago = as_of - timedelta(days=7)
    posts_7d = shorts_7d = longs_7d = 0
    for p in pieces:
        if p.published_at < week_ago:
            continue
        posts_7d += 1
        if p.kind == "short":
            shorts_7d += 1
        elif p.kind == "long":
            longs_7d += 1

    if posts_7d > 0 and not (shorts_7d >= 2 and longs_7d >= 1):
        history.append(
            {
                "id": f"cons-miss-{as_of.isocalendar()[1]}",
                "week": as_of.isocalendar()[1],
                "title": f"Current week incomplete ({shorts_7d} shorts, {longs_7d} long)",
                "category": "Consistency",
                "points": 0,
                "status": "missed",
                "date": as_of.strftime("%Y-%m-%d"),
            }
        )
    return total, history, posts_7d, shorts_7d, longs_7d


def compute_points_breakdown(
    *,
    posts: Sequence[Post],
    videos: Sequence[YouTubeVideo] | None = None,
    followers: int,
    yt_subscribers: int = 0,
    start_followers: int = 0,
    start_yt_subscribers: int = 0,
    as_of: datetime | None = None,
    from_date: datetime | None = None,
    insights: dict[str, Any] | None = None,
    growth_pts_override: int | None = None,
    include_youtube: bool = True,
) -> dict[str, Any]:
    """Return points + breakdown + task history (no profile row packaging)."""
    now = _naive_dt(as_of) or datetime.utcnow()
    window_start, window_end = clamp_scoring_window(from_date, as_of or now)
    window_start = _naive_dt(window_start) or window_start
    now = min(now, _naive_dt(window_end) or now)

    pieces = collect_pieces(
        posts,
        videos or [],
        window_start=window_start,
        window_end=now,
        include_youtube=include_youtube,
    )
    consistency, cons_history, posts_7d, shorts_7d, longs_7d = consistency_from_pieces(
        pieces, as_of=now
    )

    performance = 0
    task_history: list[dict[str, Any]] = list(cons_history)
    for piece in pieces:
        pts = performance_pts_for_piece(piece)
        performance += pts
        if pts > 0:
            task_history.append(
                {
                    "id": piece.piece_id,
                    "week": piece.published_at.isocalendar()[1],
                    "title": f"{piece.label} performance — {piece.views:,} views",
                    "category": "Performance",
                    "points": pts,
                    "status": "approved",
                    "date": piece.published_at.strftime("%Y-%m-%d"),
                }
            )
    performance_capped = min(performance, PERFORMANCE_CAP)

    if growth_pts_override is not None:
        growth = max(0, int(growth_pts_override))
    else:
        growth = growth_points_for_window(
            end_ig=int(followers or 0),
            end_yt=int(yt_subscribers or 0) if include_youtube else 0,
            start_ig=int(start_followers or 0),
            start_yt=int(start_yt_subscribers or 0) if include_youtube else 0,
        )

    cats = manual_category_points(insights)
    points = (
        consistency
        + performance_capped
        + growth
        + cats["collaborations"]
        + cats["revenue"]
        + cats["recognition"]
        + cats["participation"]
        + cats["monthly_bonuses"]
        + cats["bonus"]
    )

    return {
        "points": points,
        "consistency": consistency,
        "performance": performance_capped,
        "performance_raw": performance,
        "growth": growth,
        "collaborations": cats["collaborations"],
        "revenue": cats["revenue"],
        "recognition": cats["recognition"],
        "participation": cats["participation"],
        "monthly_bonuses": cats["monthly_bonuses"],
        "bonus": cats["bonus"],
        "posts_7d": posts_7d,
        "shorts_7d": shorts_7d,
        "longs_7d": longs_7d,
        "pieces": pieces,
        "task_history": task_history,
        "window_start": window_start,
        "window_end": now,
    }


def package_leaderboard_row(
    profile: Profile,
    posts: Sequence[Post],
    *,
    videos: Sequence[YouTubeVideo] | None = None,
    as_of: datetime | None = None,
    from_date: datetime | None = None,
    followers_override: int | None = None,
    yt_subscribers: int = 0,
    start_followers: int = 0,
    start_yt_subscribers: int = 0,
    growth_pts_override: int | None = None,
    include_youtube: bool = True,
    campus: str,
    initials: str,
) -> dict[str, Any]:
    """Full leaderboard / dashboard row with SPARK points."""
    insights = dict(getattr(profile, "insights", None) or {})
    follower_count = int(
        followers_override if followers_override is not None else (profile.followers or 0)
    )
    yt_subs = int(yt_subscribers or 0)

    scored = compute_points_breakdown(
        posts=posts,
        videos=videos,
        followers=follower_count,
        yt_subscribers=yt_subs,
        start_followers=start_followers,
        start_yt_subscribers=start_yt_subscribers,
        as_of=as_of,
        from_date=from_date,
        insights=insights,
        growth_pts_override=growth_pts_override,
        include_youtube=include_youtube,
    )

    now = scored["window_end"]
    window_start = scored["window_start"]
    pieces = scored["pieces"]
    posts_7d = scored["posts_7d"]
    points = scored["points"]

    programme_posts = 0
    total_views = total_likes = total_comments = 0
    ig_likes = ig_comments = ig_n = 0
    for post in posts:
        posted = _naive_dt(post.posted_at)
        if posted is None or posted < window_start or posted > now:
            continue
        programme_posts += 1
        ig_n += 1
        ig_likes += int(post.likes or 0)
        ig_comments += int(post.comments or 0)
        total_views += int(post.views or 0)
        total_likes += int(post.likes or 0)
        total_comments += int(post.comments or 0)

    if include_youtube and videos:
        for video in videos:
            published = _naive_dt(getattr(video, "published_at", None))
            if published is None or published < window_start or published > now:
                continue
            total_views += int(getattr(video, "view_count", 0) or 0)
            total_likes += int(getattr(video, "like_count", 0) or 0)
            total_comments += int(getattr(video, "comment_count", 0) or 0)

    if follower_count > 0 and ig_n > 0:
        engagement = round(((ig_likes + ig_comments) / ig_n / follower_count) * 100, 2)
    else:
        engagement = 0.0

    single_50k = follower_count >= 50_000 or (include_youtube and yt_subs >= 50_000)
    if single_50k:
        grit = "qualified"
    elif follower_count >= 30_000 or (include_youtube and yt_subs >= 30_000) or points >= 2000:
        grit = "striking"
    elif profile.status == ProfileStatus.FAILED or posts_7d == 0:
        grit = "at_risk"
    else:
        grit = "at_risk" if points < 500 else "striking"

    weeks_inactive = 0
    if profile.last_success_at:
        weeks_inactive = max(
            0, (now - profile.last_success_at.replace(tzinfo=None)).days // 7
        )
    elif posts_7d == 0:
        weeks_inactive = 1

    next_tier, remaining = _points_to_next(points)
    posts_30 = sum(1 for p in pieces if p.published_at >= now - timedelta(days=30))
    consistency_score = min(100, int((posts_7d / 3) * 40 + min(posts_30, 12) / 12 * 60))
    consistency = scored["consistency"]
    audience_display = follower_count + (yt_subs if include_youtube else 0)
    student = getattr(profile, "student", None) or {}
    roster_name = student.get("full_name") if isinstance(student, dict) else None
    display_name = (
        roster_name.strip()
        if isinstance(roster_name, str) and roster_name.strip()
        else (profile.full_name or profile.username)
    )

    task_history = list(scored["task_history"])
    if scored["growth"]:
        task_history.append(
            {
                "id": f"growth-{profile.id}",
                "week": now.isocalendar()[1],
                "title": (
                    f"Audience growth — IG {follower_count:,}"
                    + (f" + YT {yt_subs:,}" if include_youtube and yt_subs else "")
                    + f" (combined {audience_display:,})"
                ),
                "category": "Growth",
                "points": scored["growth"],
                "status": "approved",
                "date": now.strftime("%Y-%m-%d"),
            }
        )
    for key, label in (
        ("collaborations", "Collaborations"),
        ("revenue", "Revenue"),
        ("recognition", "Recognition"),
        ("participation", "Program participation"),
        ("monthly_bonuses", "Monthly bonus"),
        ("bonus", "Manual bonus"),
    ):
        pts = scored[key]
        if pts > 0:
            task_history.append(
                {
                    "id": f"{key}-{profile.id}",
                    "week": now.isocalendar()[1],
                    "title": label,
                    "category": label,
                    "points": pts,
                    "status": "approved",
                    "date": now.strftime("%Y-%m-%d"),
                }
            )

    for h in task_history:
        h.setdefault("profile_id", str(profile.id))
        h.setdefault("shortcode", None)

    return {
        "id": str(profile.id),
        "profile_id": str(profile.id),
        "name": display_name,
        "handle": f"@{profile.username}",
        "username": profile.username,
        "initials": initials,
        "campus": campus,
        "team": (insights.get("team") if isinstance(insights.get("team"), str) else None),
        "tier": _tier(points),
        "points": points,
        "points_breakdown": {
            "consistency": consistency,
            "performance": scored["performance"],
            "growth": scored["growth"],
            "collaborations": scored["collaborations"],
            "revenue": scored["revenue"],
            "recognition": scored["recognition"],
            "participation": scored["participation"],
            "monthly_bonuses": scored["monthly_bonuses"],
            "bonus": scored["bonus"],
        },
        "followers": follower_count,
        "views": int(total_views),
        "likes": int(total_likes),
        "comments": int(total_comments),
        "engagement": engagement,
        "avg_likes": float(profile.avg_likes or 0),
        "avg_views": float(profile.avg_views or 0),
        "avg_comments": float(profile.avg_comments or 0),
        "posts_count": programme_posts,
        "programme_posts": programme_posts,
        "ig_posts_count": int(profile.posts_count or 0),
        "posts_7d": posts_7d,
        "shorts_7d": scored["shorts_7d"],
        "longs_7d": scored["longs_7d"],
        "growth_pct_today": float(profile.growth_pct_today or 0),
        "consistency_score": consistency_score,
        "streak_weeks": (
            f"{max(1, consistency // CONSISTENCY_PTS_PER_WEEK)} wks" if consistency else "0 wks"
        ),
        "grit_status": grit,
        "weeks_inactive": weeks_inactive,
        "status": profile.status.value if hasattr(profile.status, "value") else str(profile.status),
        "last_scraped_at": profile.last_scraped_at.isoformat() if profile.last_scraped_at else None,
        "avatar_url": profile.avatar_url,
        "next_tier": next_tier,
        "points_to_next_tier": remaining,
        "task_history": sorted(task_history, key=lambda t: t.get("date") or "", reverse=True)[:20],
        "is_private": bool(profile.is_private),
        "youtube_connected": bool(getattr(profile, "youtube_connected", False)),
        "youtube_channel_id": getattr(profile, "youtube_channel_id", None),
        "youtube_subscribers": yt_subs if getattr(profile, "youtube_connected", False) else yt_subs or None,
        "youtube_views": None,
        "youtube_likes": None,
        "youtube_comments": None,
        "youtube_video_count": None,
        "combined_audience": audience_display,
        "scoring_includes_youtube": bool(include_youtube),
    }
