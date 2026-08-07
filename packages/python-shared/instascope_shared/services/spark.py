"""SPARK rankings from real scraped Instagram profiles + posts."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Literal

from instascope_shared.models import (
    DEFAULT_ORG_ID,
    Job,
    JobStatus,
    Post,
    Profile,
    ProfileSnapshot,
    ProfileStatus,
)

SortKey = Literal["overall", "points", "followers", "views", "engagement"]

GROWTH_MILESTONES = [
    (1_000, 25),
    (5_000, 75),
    (10_000, 150),
    (20_000, 300),
    (30_000, 500),
    (50_000, 1_000),
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


def _growth_pts(followers: int) -> int:
    return sum(pts for need, pts in GROWTH_MILESTONES if followers >= need)


def _short_pts(views: int) -> int:
    for minimum, pts in SHORT_BANDS:
        if views >= minimum:
            return pts
    return 0


def _long_pts(views: int) -> int:
    for minimum, pts in LONG_BANDS:
        if views >= minimum:
            return pts
    return 0


def _is_long_form(media_type: str, caption: str | None) -> bool:
    mt = (media_type or "").lower()
    if mt == "carousel":
        return True
    if mt in {"video"} and caption and len(caption) > 280:
        return True
    return False


def _initials(name: str, username: str) -> str:
    source = (name or username or "?").strip()
    parts = source.replace("@", "").split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return source[:2].upper()


SPARK_CAMPUSES = (
    "NIAT",
    "CDU",
    "NIAT Hyderabad",
    "NIAT Bengaluru",
    "NIAT Chennai",
    "CDU Vizag",
)


def _campus(profile: Profile) -> str:
    """Prefer roster university, then explicit campus insights."""
    student = getattr(profile, "student", None) or {}
    for key in ("university", "campus", "college"):
        raw = student.get(key) if isinstance(student, dict) else None
        if isinstance(raw, str) and raw.strip():
            return raw.strip()

    insights = profile.insights or {}
    raw = insights.get("campus") or insights.get("spark_campus") or insights.get("school")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()

    # Stable assignment so the same handle always keeps the same campus
    key = (profile.username or str(profile.id) or "spark").lower().encode("utf-8")
    return SPARK_CAMPUSES[sum(key) % len(SPARK_CAMPUSES)]


def _post_performance_pts(post: Post) -> tuple[int, bool, str]:
    """Return (points, is_long_form, media_type) for a post."""
    views = int(post.views or 0)
    mt = str(post.media_type.value if hasattr(post.media_type, "value") else post.media_type)
    long_form = _is_long_form(mt, post.caption)
    pts = _long_pts(views) if long_form else _short_pts(views)
    return pts, long_form, mt


def _naive_dt(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=None) if value.tzinfo else value


def compute_spark_points(
    posts: list[Post],
    followers: int,
    *,
    as_of: datetime | None = None,
    from_date: datetime | None = None,
) -> int:
    """Raw SPARK points (consistency + capped performance + growth) as of a timestamp."""
    now = _naive_dt(as_of) or datetime.utcnow()
    window_start = _naive_dt(from_date)
    week_ago = now - timedelta(days=7)
    consistency = 0
    posts_7d = 0
    shorts_7d = 0
    longs_7d = 0
    performance = 0

    for post in posts:
        posted = post.posted_at
        posted_naive = _naive_dt(posted)
        if window_start is not None:
            if posted_naive is None or posted_naive < window_start:
                continue
        if as_of and posted_naive and posted_naive > now:
            continue
        pts, long_form, mt = _post_performance_pts(post)
        performance += pts
        if posted_naive and posted_naive >= week_ago:
            posts_7d += 1
            if long_form or mt == "carousel":
                longs_7d += 1
            else:
                shorts_7d += 1

    if (shorts_7d >= 2 and longs_7d >= 1) or posts_7d >= 3:
        consistency = 10

    return consistency + min(performance, 3000) + _growth_pts(int(followers or 0))


def score_profile(
    profile: Profile,
    posts: list[Post],
    *,
    as_of: datetime | None = None,
    from_date: datetime | None = None,
    followers_override: int | None = None,
) -> dict[str, Any]:
    """Compute SPARK points from real scrape metrics."""
    now = _naive_dt(as_of) or datetime.utcnow()
    window_start = _naive_dt(from_date)
    week_ago = now - timedelta(days=7)
    follower_count = int(followers_override if followers_override is not None else (profile.followers or 0))

    consistency = 0
    posts_7d = 0
    shorts_7d = 0
    longs_7d = 0
    performance = 0
    total_views = 0
    total_likes = 0
    total_comments = 0
    task_history: list[dict[str, Any]] = []

    for post in posts:
        posted = post.posted_at
        posted_naive = _naive_dt(posted)
        if window_start is not None:
            # Period mode: posts without posted_at cannot be attributed to the window.
            if posted_naive is None or posted_naive < window_start:
                continue
        if as_of and posted_naive and posted_naive > now:
            continue

        views = int(post.views or 0)
        likes = int(post.likes or 0)
        comments = int(post.comments or 0)
        total_views += views
        total_likes += likes
        total_comments += comments

        pts, long_form, mt = _post_performance_pts(post)
        performance += pts

        if posted_naive and posted_naive >= week_ago:
            posts_7d += 1
            if long_form or mt == "carousel":
                longs_7d += 1
            else:
                shorts_7d += 1

        if pts > 0:
            task_history.append(
                {
                    "id": str(post.id),
                    "week": posted.isocalendar()[1] if posted else 0,
                    "title": f"{'Long-form' if long_form else 'Short-form'} performance — {views:,} views",
                    "category": "Performance",
                    "points": pts,
                    "status": "approved",
                    "date": posted.strftime("%Y-%m-%d") if posted else "",
                    "profile_id": str(profile.id),
                    "shortcode": post.shortcode,
                }
            )

    # Weekly consistency: 2 shorts + 1 long ≈ 3 posts with mix, or 3+ posts in week
    if shorts_7d >= 2 and longs_7d >= 1:
        consistency = 10
        task_history.append(
            {
                "id": f"cons-{profile.id}",
                "week": now.isocalendar()[1],
                "title": "Weekly minimum — 2 shorts + 1 long-form",
                "category": "Consistency",
                "points": 10,
                "status": "approved",
                "date": now.strftime("%Y-%m-%d"),
                "profile_id": str(profile.id),
                "shortcode": None,
            }
        )
    elif posts_7d >= 3:
        consistency = 10
        task_history.append(
            {
                "id": f"cons-{profile.id}",
                "week": now.isocalendar()[1],
                "title": "Weekly minimum met (3+ posts this week)",
                "category": "Consistency",
                "points": 10,
                "status": "approved",
                "date": now.strftime("%Y-%m-%d"),
                "profile_id": str(profile.id),
                "shortcode": None,
            }
        )
    elif posts_7d > 0:
        task_history.append(
            {
                "id": f"cons-miss-{profile.id}",
                "week": now.isocalendar()[1],
                "title": f"Weekly minimum incomplete ({posts_7d} posts)",
                "category": "Consistency",
                "points": 0,
                "status": "missed",
                "date": now.strftime("%Y-%m-%d"),
                "profile_id": str(profile.id),
                "shortcode": None,
            }
        )

    growth = _growth_pts(follower_count)
    if growth:
        task_history.append(
            {
                "id": f"growth-{profile.id}",
                "week": now.isocalendar()[1],
                "title": f"Audience growth milestones — {follower_count:,} followers",
                "category": "Growth",
                "points": growth,
                "status": "approved",
                "date": now.strftime("%Y-%m-%d"),
                "profile_id": str(profile.id),
                "shortcode": None,
            }
        )

    # Cap performance contribution for fairness (theoretical unbounded otherwise)
    performance_capped = min(performance, 3000)
    bonus = 0
    try:
        bonus = int((profile.insights or {}).get("spark_bonus_points") or 0)
    except (TypeError, ValueError):
        bonus = 0
    points = consistency + performance_capped + growth + max(0, bonus)

    # Consistency score 0-100 from recent posting
    insights = profile.insights or {}
    posts_30 = int(insights.get("posts_last_30d") or 0) if window_start is None else 0
    if posts_30 == 0:
        posts_30 = sum(
            1
            for p in posts
            if p.posted_at
            and (window_start is None or _naive_dt(p.posted_at) >= window_start)
            and _naive_dt(p.posted_at) >= now - timedelta(days=30)
            and (not as_of or _naive_dt(p.posted_at) <= now)
        )
    consistency_score = min(100, int((posts_7d / 3) * 40 + min(posts_30, 12) / 12 * 60))

    engagement = float(profile.engagement_rate or 0)
    if window_start is not None:
        # Period board: rate from posts in the selected window only.
        period_posts = sum(
            1
            for p in posts
            if p.posted_at
            and _naive_dt(p.posted_at) is not None
            and _naive_dt(p.posted_at) >= window_start
            and (not as_of or _naive_dt(p.posted_at) <= now)
        )
        if follower_count > 0 and period_posts > 0:
            avg_eng = (total_likes + total_comments) / period_posts
            engagement = round((avg_eng / follower_count) * 100, 2)
        else:
            engagement = 0.0
    elif engagement <= 0 and profile.followers:
        avg_eng = (float(profile.avg_likes or 0) + float(profile.avg_comments or 0))
        engagement = round((avg_eng / max(profile.followers, 1)) * 100, 2)

    grit = "not_eligible"
    if follower_count >= 50_000:
        grit = "qualified"
    elif follower_count >= 30_000 or points >= 2000:
        grit = "striking"
    elif profile.status == ProfileStatus.FAILED or posts_7d == 0:
        grit = "at_risk"
    else:
        grit = "at_risk" if points < 500 else "striking"

    weeks_inactive = 0
    if profile.last_success_at:
        weeks_inactive = max(0, (now - profile.last_success_at.replace(tzinfo=None)).days // 7)
    elif posts_7d == 0:
        weeks_inactive = 1

    next_tier, remaining = _points_to_next(points)

    use_period_totals = window_start is not None
    return {
        "id": str(profile.id),
        "profile_id": str(profile.id),
        "name": profile.full_name or profile.username,
        "handle": f"@{profile.username}",
        "username": profile.username,
        "initials": _initials(profile.full_name or "", profile.username),
        "campus": _campus(profile),
        "team": (insights.get("team") if isinstance(insights.get("team"), str) else None),
        "tier": _tier(points),
        "points": points,
        "points_breakdown": {
            "consistency": consistency,
            "performance": performance_capped,
            "growth": growth,
            "bonus": max(0, bonus),
        },
        "followers": follower_count,
        "views": int(total_views if use_period_totals else (total_views or insights.get("total_views_sampled") or 0)),
        "likes": int(total_likes if use_period_totals else (total_likes or insights.get("total_likes_sampled") or 0)),
        "comments": int(
            total_comments if use_period_totals else (total_comments or insights.get("total_comments_sampled") or 0)
        ),
        "engagement": engagement,
        "avg_likes": float(profile.avg_likes or 0),
        "avg_views": float(profile.avg_views or 0),
        "avg_comments": float(profile.avg_comments or 0),
        "posts_count": int(profile.posts_count or 0),
        "posts_7d": posts_7d,
        "growth_pct_today": float(profile.growth_pct_today or 0),
        "consistency_score": consistency_score,
        "streak_weeks": f"{max(1, posts_30 // 3)} wks" if posts_30 else "0 wks",
        "grit_status": grit,
        "weeks_inactive": weeks_inactive,
        "status": profile.status.value if hasattr(profile.status, "value") else str(profile.status),
        "last_scraped_at": profile.last_scraped_at.isoformat() if profile.last_scraped_at else None,
        "avatar_url": profile.avatar_url,
        "next_tier": next_tier,
        "points_to_next_tier": remaining,
        "task_history": sorted(task_history, key=lambda t: t.get("date") or "", reverse=True)[:20],
        "is_private": bool(profile.is_private),
    }


async def _profiles_for_org(org_id: str | None = None) -> list[Profile]:
    oid = org_id or DEFAULT_ORG_ID
    profiles = await Profile.find(Profile.org_id == oid).to_list()
    # Include legacy profiles missing org_id so shared cohort works pre-backfill
    all_profiles = await Profile.find_all().to_list()
    legacy = [p for p in all_profiles if not getattr(p, "org_id", None)]
    if not profiles and legacy:
        return legacy
    if legacy:
        seen = {str(p.id) for p in profiles}
        for p in legacy:
            if str(p.id) not in seen:
                profiles.append(p)
    return profiles


async def _posts_for_profiles(profile_ids: list[str]) -> dict[str, list[Post]]:
    by: dict[str, list[Post]] = defaultdict(list)
    if not profile_ids:
        return by
    # Chunk to avoid huge $in if needed; day-1 load all matching
    posts = await Post.find({"profile_id": {"$in": profile_ids}}).to_list()
    for p in posts:
        by[p.profile_id].append(p)
    return by


def _latest_snap_by_profile(snaps: list[ProfileSnapshot]) -> dict[str, ProfileSnapshot]:
    latest: dict[str, ProfileSnapshot] = {}
    for s in snaps:
        cur = latest.get(s.profile_id)
        if not cur or s.snapshot_date > cur.snapshot_date:
            latest[s.profile_id] = s
    return latest


async def build_leaderboard(
    org_id: str | None = None,
    *,
    sort: SortKey = "overall",
    profiles: list[Profile] | None = None,
    posts_map: dict[str, list[Post]] | None = None,
    you_profile_id: str | None = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
) -> list[dict[str, Any]]:
    oid = org_id or DEFAULT_ORG_ID
    if profiles is None:
        profiles = await _profiles_for_org(oid)
    profile_ids = [str(p.id) for p in profiles]
    if posts_map is None:
        posts_map = await _posts_for_profiles(profile_ids)

    window_start = _naive_dt(from_date)
    window_end = _naive_dt(to_date)
    period_mode = window_start is not None or window_end is not None

    # Previous ranks: on/before from_date when ranged, else ~7 days ago (followers proxy)
    if period_mode and window_start is not None:
        prev_cutoff = window_start.strftime("%Y-%m-%d")
    else:
        prev_cutoff = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")

    prev_snaps = (
        await ProfileSnapshot.find(
            {"profile_id": {"$in": profile_ids}, "snapshot_date": {"$lte": prev_cutoff}}
        ).to_list()
        if profile_ids
        else []
    )
    latest_prev = _latest_snap_by_profile(prev_snaps)
    prev_followers = {pid: s.followers for pid, s in latest_prev.items()}
    prev_order = sorted(prev_followers.items(), key=lambda x: x[1], reverse=True)
    prev_rank = {pid: i + 1 for i, (pid, _) in enumerate(prev_order)}

    followers_at_end: dict[str, int] = {}
    if period_mode and window_end is not None and profile_ids:
        end_cutoff = window_end.strftime("%Y-%m-%d")
        end_snaps = await ProfileSnapshot.find(
            {"profile_id": {"$in": profile_ids}, "snapshot_date": {"$lte": end_cutoff}}
        ).to_list()
        for pid, snap in _latest_snap_by_profile(end_snaps).items():
            followers_at_end[pid] = int(snap.followers or 0)

    rows: list[dict[str, Any]] = []
    for p in profiles:
        pid = str(p.id)
        score_kwargs: dict[str, Any] = {}
        if period_mode:
            score_kwargs["from_date"] = window_start
            score_kwargs["as_of"] = window_end
            if pid in followers_at_end:
                score_kwargs["followers_override"] = followers_at_end[pid]
        rows.append(score_profile(p, posts_map.get(pid, []), **score_kwargs))

    def sort_key(r: dict[str, Any]) -> tuple:
        if sort == "followers":
            return (-r["followers"], -r["points"])
        if sort == "views":
            return (-r["views"], -r["points"])
        if sort == "engagement":
            return (-r["engagement"], -r["points"])
        # overall / points
        return (-r["points"], -r["followers"], -r["views"])

    rows.sort(key=sort_key)
    for i, r in enumerate(rows):
        r["rank"] = i + 1
        r["prev_rank"] = prev_rank.get(r["id"], i + 1)
        r["rank_delta"] = r["prev_rank"] - r["rank"]
        r["is_you"] = bool(you_profile_id and r["id"] == you_profile_id)
    return rows


async def get_top_10(org_id: str | None = None) -> dict[str, Any]:
    board = await build_leaderboard(org_id, sort="overall")
    return {
        "items": board[:10],
        "total_creators": len(board),
        "week_label": f"LIVE • {datetime.utcnow().strftime('%d %b %Y')}",
    }


async def get_student_dashboard(org_id: str, profile_id: str) -> dict[str, Any]:
    board = await build_leaderboard(org_id, sort="overall", you_profile_id=profile_id)
    if not board:
        return {"empty": True, "creators": [], "creator": None}

    creator = next((r for r in board if r["id"] == profile_id), None)
    if not creator:
        return {"empty": True, "creators": [], "creator": None, "error": "Profile not on leaderboard"}

    profile = await Profile.get(profile_id)
    posts = await Post.find(Post.profile_id == profile_id).sort(-Post.posted_at).to_list()

    # Performance series from snapshots
    snaps = (
        await ProfileSnapshot.find(ProfileSnapshot.profile_id == creator["id"])
        .sort(+ProfileSnapshot.snapshot_date)
        .to_list()
    )
    performance = [
        {
            "date": s.snapshot_date[-5:] if len(s.snapshot_date) >= 5 else s.snapshot_date,
            "views": s.avg_views,
            "points": 0,
            "followers": s.followers,
            "likes": s.avg_likes,
            "engagement": s.engagement_rate,
        }
        for s in snaps[-30:]
    ]
    if not performance:
        performance = [
            {
                "date": "now",
                "views": creator["avg_views"],
                "points": creator["points"],
                "followers": creator["followers"],
                "likes": creator["avg_likes"],
                "engagement": creator["engagement"],
            }
        ]
    if performance:
        performance[-1]["points"] = creator["points"]

    followers_delta = 0
    if len(snaps) >= 2:
        followers_delta = snaps[-1].followers - snaps[-2].followers
    elif creator["growth_pct_today"]:
        followers_delta = int(creator["followers"] * (creator["growth_pct_today"] / 100))

    top = [r for r in board if not r.get("is_you")][:5]

    recent_posts = [
        {
            "id": str(p.id),
            "shortcode": p.shortcode,
            "media_type": p.media_type.value if hasattr(p.media_type, "value") else str(p.media_type),
            "caption": (p.caption or "")[:200],
            "likes": int(p.likes or 0),
            "comments": int(p.comments or 0),
            "views": int(p.views or 0),
            "posted_at": p.posted_at.isoformat() if p.posted_at else None,
            "permalink": p.permalink,
        }
        for p in posts[:20]
    ]

    history = [
        {
            "id": str(s.id),
            "snapshot_date": s.snapshot_date,
            "followers": s.followers,
            "following": s.following,
            "posts_count": s.posts_count,
            "avg_likes": s.avg_likes,
            "avg_views": s.avg_views,
            "engagement_rate": s.engagement_rate,
            "followers_growth": s.followers_growth,
            "followers_growth_pct": s.followers_growth_pct,
        }
        for s in reversed(snaps[-30:])
    ]

    return {
        "empty": False,
        "week_label": f"LIVE • {datetime.utcnow().strftime('%d %b %Y')}",
        "refresh_note": "Stats from live Instagram scrapes",
        "creator": creator,
        "top_creators": top,
        "leaderboard": board,
        "performance": performance,
        "followers_delta": followers_delta,
        "task_history": creator.get("task_history") or [],
        "total_participants": len(board),
        "in_top_10": creator["rank"] <= 10,
        "insights": dict(getattr(profile, "insights", None) or {}) if profile else {},
        "recent_posts": recent_posts,
        "history": history,
        "profile": {
            "bio": getattr(profile, "bio", None) if profile else None,
            "website": getattr(profile, "website", None) if profile else None,
            "is_verified": bool(getattr(profile, "is_verified", False)) if profile else False,
            "is_private": bool(getattr(profile, "is_private", False)) if profile else False,
            "is_business": bool(getattr(profile, "is_business", False)) if profile else False,
            "category": getattr(profile, "category", None) if profile else None,
            "following": int(getattr(profile, "following", 0) or 0) if profile else 0,
            "student": dict(getattr(profile, "student", None) or {}) if profile else {},
            "last_scraped_at": profile.last_scraped_at.isoformat() if profile and profile.last_scraped_at else None,
        },
    }


async def get_admin_overview(org_id: str | None = None) -> dict[str, Any]:
    oid = org_id or DEFAULT_ORG_ID
    profiles = await _profiles_for_org(oid)
    posts_map = await _posts_for_profiles([str(p.id) for p in profiles])
    board = await build_leaderboard(oid, sort="overall", profiles=profiles, posts_map=posts_map)
    # Flatten posts once (already loaded for scoring)
    posts = [p for bucket in posts_map.values() for p in bucket]
    today = datetime.utcnow().strftime("%Y-%m-%d")

    total_followers = sum(p.followers for p in profiles)
    total_views = sum(int(r["views"]) for r in board)
    total_likes = sum(int(r["likes"]) for r in board)
    total_comments = sum(int(r["comments"]) for r in board)
    total_points = sum(int(r["points"]) for r in board)
    reels = sum(1 for p in posts if str(getattr(p.media_type, "value", p.media_type)).lower() == "reel")

    # Fast WoW: points added in the last 7 days (new post performance + consistency + growth milestone deltas)
    week_ago_dt = datetime.utcnow() - timedelta(days=7)
    week_ago_str = week_ago_dt.strftime("%Y-%m-%d")

    week_perf = 0
    for p in posts:
        posted = p.posted_at
        if not posted:
            continue
        if posted.replace(tzinfo=None) >= week_ago_dt:
            week_perf += _post_performance_pts(p)[0]

    week_cons = sum(int((r.get("points_breakdown") or {}).get("consistency") or 0) for r in board)

    # Reuse 14d snaps for growth series + WoW growth deltas (skip full historical re-score)
    since = (datetime.utcnow() - timedelta(days=14)).strftime("%Y-%m-%d")
    profile_ids = [str(p.id) for p in profiles]
    snaps = (
        await ProfileSnapshot.find(
            {"profile_id": {"$in": profile_ids}, "snapshot_date": {"$gte": since}}
        ).to_list()
        if profile_ids
        else []
    )

    prev_snap_best: dict[str, tuple[str, int]] = {}
    for s in snaps:
        if s.snapshot_date > week_ago_str:
            continue
        pid = str(s.profile_id)
        prev = prev_snap_best.get(pid)
        if prev is None or s.snapshot_date >= prev[0]:
            prev_snap_best[pid] = (s.snapshot_date, int(s.followers or 0))

    week_growth = 0
    for profile in profiles:
        pid = str(profile.id)
        cur_g = _growth_pts(int(profile.followers or 0))
        # No prior snap → treat growth as unchanged for WoW (avoids a second full snapshot scan)
        prev_fol = prev_snap_best[pid][1] if pid in prev_snap_best else int(profile.followers or 0)
        week_growth += max(0, cur_g - _growth_pts(prev_fol))

    week_awarded = week_perf + week_cons + week_growth
    prev_total_points = max(0, total_points - week_awarded)
    if prev_total_points > 0:
        points_wow_pct = round((week_awarded / prev_total_points) * 100, 1)
    elif total_points > 0:
        points_wow_pct = 100.0
    else:
        points_wow_pct = 0.0

    def _date_str(dt: datetime | None) -> str | None:
        if not dt:
            return None
        return dt.strftime("%Y-%m-%d")

    def _has_ig_card(p: Any) -> bool:
        """Unique success signal: real IG card data (one profile counted once)."""
        return bool(p.last_success_at) or int(p.followers or 0) > 0 or int(p.posts_count or 0) > 0

    def _progress_active(p: Any) -> bool:
        prog = getattr(p, "scrape_progress", None) or {}
        return bool(prog.get("active"))

    updated_today = sum(1 for p in profiles if _date_str(p.last_success_at) == today)
    failed = sum(1 for p in profiles if p.status == ProfileStatus.FAILED)
    unavailable = sum(1 for p in profiles if p.status == ProfileStatus.UNAVAILABLE)
    paused = sum(1 for p in profiles if p.status == ProfileStatus.PAUSED)
    private = sum(1 for p in profiles if p.is_private)
    scraped_successfully = sum(1 for p in profiles if _has_ig_card(p))
    # Pending = roster rows that never got a usable card and are not terminal statuses.
    pending = sum(
        1
        for p in profiles
        if not _has_ig_card(p)
        and p.status
        not in {ProfileStatus.FAILED, ProfileStatus.UNAVAILABLE, ProfileStatus.PAUSED}
    )
    private_scraped = sum(1 for p in profiles if p.is_private and _has_ig_card(p))
    private_pending = sum(1 for p in profiles if p.is_private and not _has_ig_card(p))

    failed_today = sum(
        1
        for p in profiles
        if p.status == ProfileStatus.FAILED
        and (
            _date_str(p.last_scraped_at) == today
            or _date_str(getattr(p, "updated_at", None)) == today
        )
    )
    private_updated_today = sum(
        1 for p in profiles if p.is_private and _date_str(p.last_success_at) == today
    )
    in_queue = sum(1 for p in profiles if _progress_active(p))
    inactive = sum(1 for r in board if r["posts_7d"] == 0)

    grit = {
        "qualified": sum(1 for r in board if r["grit_status"] == "qualified"),
        "striking": sum(1 for r in board if r["grit_status"] == "striking"),
        "at_risk": sum(1 for r in board if r["grit_status"] in {"at_risk", "not_eligible"}),
    }

    # Jobs as submission proxy (org-wide via profile owners)
    user_ids = list({p.user_id for p in profiles if p.user_id})
    jobs = []
    if user_ids:
        jobs = await Job.find({"user_id": {"$in": user_ids}}).sort(-Job.created_at).limit(200).to_list()
    submissions = {
        "pending": sum(1 for j in jobs if j.status in {JobStatus.PENDING, JobStatus.RUNNING, JobStatus.RETRYING}),
        "approved": sum(1 for j in jobs if j.status == JobStatus.SUCCESS),
        "rejected": sum(1 for j in jobs if j.status == JobStatus.FAILED),
    }

    by_date: dict[str, dict[str, float]] = defaultdict(lambda: {"followers": 0.0, "views": 0.0, "likes": 0.0, "n": 0})
    for s in snaps:
        bucket = by_date[s.snapshot_date]
        bucket["followers"] += s.followers
        bucket["views"] += s.avg_views
        bucket["likes"] += s.avg_likes
        bucket["n"] += 1
    growth_series = [
        {
            "date": d,
            "followers": round(v["followers"], 0),
            "views": round(v["views"], 0),
            "likes": round(v["likes"], 0),
        }
        for d, v in sorted(by_date.items())
    ]

    insights = []
    if board:
        by_growth = sorted(board, key=lambda r: r["growth_pct_today"], reverse=True)
        by_eng = sorted(board, key=lambda r: r["engagement"], reverse=True)
        by_posts = sorted(board, key=lambda r: r["posts_7d"], reverse=True)
        by_rise = sorted(board, key=lambda r: r["rank_delta"], reverse=True)
        by_views = sorted(board, key=lambda r: r["views"], reverse=True)
        insights = [
            {"label": "Highest Follower Growth", "name": by_growth[0]["name"], "value": f"{by_growth[0]['growth_pct_today']:+.2f}%"},
            {"label": "Highest Engagement Rate", "name": by_eng[0]["name"], "value": f"{by_eng[0]['engagement']}%"},
            {"label": "Most Consistent Creator", "name": by_posts[0]["name"], "value": f"{by_posts[0]['posts_7d']} posts/7d"},
            {"label": "Fastest Rising", "name": by_rise[0]["name"], "value": f"+{by_rise[0]['rank_delta']} ranks"},
            {"label": "Most Viewed Portfolio", "name": by_views[0]["name"], "value": f"{by_views[0]['views']:,} views"},
        ]

    needing = [
        {"label": "No post in 7+ days", "count": inactive},
        {"label": "Scraping failed", "count": failed},
        {"label": "IG username missing", "count": unavailable},
        {"label": "Account is private", "count": private},
        {"label": "Not scraped yet", "count": pending},
        {"label": "At-risk / inactive flags", "count": grit["at_risk"]},
    ]

    avg_eng = round(sum(r["engagement"] for r in board) / len(board), 2) if board else 0.0
    n_profiles = len(profiles) or 1
    avg_followers = round(total_followers / n_profiles, 0) if profiles else 0
    avg_likes = round(sum(int(p.avg_likes or 0) for p in profiles) / n_profiles, 0) if profiles else 0
    avg_views = round(sum(int(p.avg_views or 0) for p in profiles) / n_profiles, 0) if profiles else 0
    follower_growth_today = sum(
        max(0, int(p.followers * (p.growth_pct_today / 100))) for p in profiles
    )

    last_sync_dt = max((p.last_success_at for p in profiles if p.last_success_at), default=None)

    # Content mix + posts/day + heatmap (InstaScope overview parity)
    type_counts: dict[str, int] = defaultdict(int)
    posts_by_day: dict[str, int] = defaultdict(int)
    heatmap: dict[tuple[int, int], int] = defaultdict(int)
    for post in posts:
        mt = str(getattr(post.media_type, "value", post.media_type) or "unknown").lower()
        type_counts[mt] += 1
        if post.posted_at:
            posts_by_day[post.posted_at.strftime("%Y-%m-%d")] += 1
            heatmap[(post.posted_at.weekday(), post.posted_at.hour)] += 1
    content_types = [
        {"name": k, "value": float(v)} for k, v in sorted(type_counts.items(), key=lambda x: -x[1])
    ]
    posts_per_day = [
        {"date": d, "value": float(c)} for d, c in sorted(posts_by_day.items())[-30:]
    ]
    posting_heatmap = [{"day": d, "hour": h, "count": c} for (d, h), c in heatmap.items()]

    # Portfolio-average followers over time (old overview chart)
    by_date_followers: dict[str, list[int]] = defaultdict(list)
    for s in snaps:
        by_date_followers[s.snapshot_date].append(int(s.followers or 0))
    followers_over_time = [
        {"date": d, "value": round(sum(vals) / len(vals), 2)}
        for d, vals in sorted(by_date_followers.items())
    ]

    recent_sorted = sorted(
        profiles,
        key=lambda p: p.last_scraped_at or p.updated_at or datetime.min,
        reverse=True,
    )
    recent_updates = [
        {
            "id": str(p.id),
            "username": p.username,
            "full_name": p.full_name or (p.student or {}).get("full_name"),
            "followers": int(p.followers or 0),
            "following": int(p.following or 0),
            "posts_count": int(p.posts_count or 0),
            "avg_likes": int(p.avg_likes or 0),
            "avg_views": int(p.avg_views or 0),
            "avg_comments": int(getattr(p, "avg_comments", 0) or 0),
            "engagement_rate": float(p.engagement_rate or 0),
            "growth_pct_today": float(p.growth_pct_today or 0),
            "status": p.status.value if hasattr(p.status, "value") else str(p.status),
            "is_verified": bool(p.is_verified),
            "is_private": bool(p.is_private),
            "is_business": bool(getattr(p, "is_business", False)),
            "category": getattr(p, "category", None),
            "bio": (p.bio or "")[:160] if getattr(p, "bio", None) else None,
            "website": getattr(p, "website", None),
            "follower_following_ratio": float(getattr(p, "follower_following_ratio", 0) or 0),
            "highlight_reel_count": int(getattr(p, "highlight_reel_count", 0) or 0),
            "last_scraped_at": p.last_scraped_at.isoformat() if p.last_scraped_at else None,
            "last_error": p.last_error,
            "student_id": (p.student or {}).get("student_id"),
            "campus": (p.student or {}).get("university") or "—",
            "full_name_student": (p.student or {}).get("full_name"),
        }
        for p in recent_sorted[:50]
    ]

    # Full portfolio cards for analytics grid (all tracked creators)
    portfolio = [
        {
            "id": str(p.id),
            "username": p.username,
            "full_name": p.full_name or (p.student or {}).get("full_name"),
            "followers": int(p.followers or 0),
            "following": int(p.following or 0),
            "posts_count": int(p.posts_count or 0),
            "avg_likes": int(p.avg_likes or 0),
            "avg_views": int(p.avg_views or 0),
            "avg_comments": int(getattr(p, "avg_comments", 0) or 0),
            "engagement_rate": float(p.engagement_rate or 0),
            "growth_pct_today": float(p.growth_pct_today or 0),
            "status": p.status.value if hasattr(p.status, "value") else str(p.status),
            "is_verified": bool(p.is_verified),
            "is_private": bool(p.is_private),
            "campus": (p.student or {}).get("university") or "—",
            "student_id": (p.student or {}).get("student_id"),
            "last_scraped_at": p.last_scraped_at.isoformat() if p.last_scraped_at else None,
        }
        for p in sorted(profiles, key=lambda x: int(x.followers or 0), reverse=True)
    ]

    # Live alerts from scrape health + growth (complements /notifications)
    alerts: list[dict[str, Any]] = []
    for p in profiles:
        if p.status == ProfileStatus.FAILED or p.status == ProfileStatus.UNAVAILABLE:
            alerts.append(
                {
                    "id": f"fail-{p.id}",
                    "type": "scrape_failed",
                    "severity": "high",
                    "title": f"Scrape failed for @{p.username}",
                    "body": (p.last_error or "Unknown scrape error")[:220],
                    "profile_id": str(p.id),
                    "username": p.username,
                    "created_at": (p.last_scraped_at or p.updated_at or datetime.utcnow()).isoformat(),
                }
            )
        elif p.is_private:
            alerts.append(
                {
                    "id": f"priv-{p.id}",
                    "type": "profile_private",
                    "severity": "medium",
                    "title": f"@{p.username} is private",
                    "body": "Private accounts block full post pagination and metrics.",
                    "profile_id": str(p.id),
                    "username": p.username,
                    "created_at": (p.updated_at or datetime.utcnow()).isoformat(),
                }
            )
        g = float(p.growth_pct_today or 0)
        if abs(g) >= 2.0 and int(p.followers or 0) > 0:
            alerts.append(
                {
                    "id": f"growth-{p.id}",
                    "type": "followers_up" if g > 0 else "followers_down",
                    "severity": "medium",
                    "title": f"@{p.username} {'grew' if g > 0 else 'dropped'} {g:+.2f}%",
                    "body": f"Follower change vs previous scrape · {int(p.followers):,} followers now.",
                    "profile_id": str(p.id),
                    "username": p.username,
                    "created_at": (p.last_success_at or p.updated_at or datetime.utcnow()).isoformat(),
                }
            )
    alerts.sort(key=lambda a: a["created_at"], reverse=True)
    alerts = alerts[:25]

    return {
        "week_label": f"LIVE • {datetime.utcnow().strftime('%d %b %Y')}",
        "date_range": f"{since} → {today}",
        "total_participants": len(profiles),
        "ig_connected_pct": 100 if profiles else 0,
        "total_followers": total_followers,
        "total_views": total_views,
        "total_likes": total_likes,
        "total_comments": total_comments,
        "total_points_distributed": total_points,
        "points_wow_pct": points_wow_pct,
        "total_engagement": total_likes + total_comments,
        "average_engagement": avg_eng,
        "average_followers": avg_followers,
        "average_likes": avg_likes,
        "average_views": avg_views,
        "follower_growth_today": follower_growth_today,
        "profiles_updated_today": updated_today,
        "failed_updates": failed,
        "reels_posted": reels,
        "new_followers": follower_growth_today,
        "growth_series": growth_series,
        "followers_over_time": followers_over_time,
        "content_types": content_types,
        "posts_per_day": posts_per_day,
        "posting_heatmap": posting_heatmap,
        "recent_updates": recent_updates,
        "portfolio": portfolio,
        "alerts": alerts,
        "insights": insights,
        "needing_attention": needing,
        # Lifetime unique counts (1 profile = 1 count; re-scrapes do not inflate).
        "overall": {
            "total_profiles": len(profiles),
            "scraped_successfully": scraped_successfully,
            "failed": failed,
            "unavailable": unavailable,
            "paused": paused,
            "pending": pending,
            "private": private,
            "private_scraped": private_scraped,
            "private_pending": private_pending,
            "total_followers": total_followers,
            "total_views": total_views,
            "total_likes": total_likes,
            "total_comments": total_comments,
            "total_engagement": total_likes + total_comments,
            "total_points": total_points,
            "reels_posted": reels,
            "average_engagement": avg_eng,
            "average_followers": avg_followers,
            "average_likes": avg_likes,
            "average_views": avg_views,
            "at_risk_count": grit["at_risk"],
            "coverage_pct": round(100 * scraped_successfully / len(profiles), 1) if profiles else 0.0,
        },
        # Calendar-day metrics (UTC date of last_success_at / last_scraped_at).
        "today": {
            "updated": updated_today,
            "failed": failed_today,
            "private_updated": private_updated_today,
            "follower_growth": follower_growth_today,
            "in_queue": in_queue,
            "date": today,
        },
        "scrape": {
            "tracked": len(profiles),
            "updated_today": updated_today,
            "failed": failed,
            "scraped_successfully": scraped_successfully,
            "unavailable": unavailable,
            "pending": pending,
            "private": private,
            "in_queue": in_queue,
            "last_sync": last_sync_dt.isoformat() if last_sync_dt else None,
            "next_sync": "Daily scrape / on Refresh",
        },
        "grit": grit,
        "submissions": submissions,
        "at_risk_count": grit["at_risk"],
        "leaderboard_preview": board[:8],
    }
