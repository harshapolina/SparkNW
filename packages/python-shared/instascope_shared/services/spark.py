"""SPARK rankings from real scraped Instagram profiles + posts."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Literal

from instascope_shared.models import Job, JobStatus, Post, Profile, ProfileSnapshot, ProfileStatus

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
    """Prefer explicit campus on the profile; otherwise spread creators across campuses."""
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


def compute_spark_points(
    posts: list[Post],
    followers: int,
    *,
    as_of: datetime | None = None,
) -> int:
    """Raw SPARK points (consistency + capped performance + growth) as of a timestamp."""
    now = as_of.replace(tzinfo=None) if as_of and as_of.tzinfo else (as_of or datetime.utcnow())
    week_ago = now - timedelta(days=7)
    consistency = 0
    posts_7d = 0
    shorts_7d = 0
    longs_7d = 0
    performance = 0

    for post in posts:
        posted = post.posted_at
        posted_naive = posted.replace(tzinfo=None) if posted else None
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
    followers_override: int | None = None,
) -> dict[str, Any]:
    """Compute SPARK points from real scrape metrics."""
    now = as_of.replace(tzinfo=None) if as_of and as_of.tzinfo else (as_of or datetime.utcnow())
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
        posted_naive = posted.replace(tzinfo=None) if posted else None
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
    points = consistency + performance_capped + growth

    # Consistency score 0-100 from recent posting
    insights = profile.insights or {}
    posts_30 = int(insights.get("posts_last_30d") or 0)
    if posts_30 == 0:
        posts_30 = sum(
            1
            for p in posts
            if p.posted_at and p.posted_at.replace(tzinfo=None) >= now - timedelta(days=30)
        )
    consistency_score = min(100, int((posts_7d / 3) * 40 + min(posts_30, 12) / 12 * 60))

    engagement = float(profile.engagement_rate or 0)
    if engagement <= 0 and profile.followers:
        avg_eng = (float(profile.avg_likes or 0) + float(profile.avg_comments or 0))
        engagement = round((avg_eng / max(profile.followers, 1)) * 100, 2)

    grit = "not_eligible"
    if profile.followers >= 50_000:
        grit = "qualified"
    elif profile.followers >= 30_000 or points >= 2000:
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
        },
        "followers": follower_count,
        "views": int(total_views or insights.get("total_views_sampled") or 0),
        "likes": int(total_likes or insights.get("total_likes_sampled") or 0),
        "comments": int(total_comments or insights.get("total_comments_sampled") or 0),
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


async def _posts_by_profile(user_id: str) -> dict[str, list[Post]]:
    posts = await Post.find(Post.user_id == user_id).to_list()
    by: dict[str, list[Post]] = defaultdict(list)
    for p in posts:
        by[p.profile_id].append(p)
    return by


async def build_leaderboard(
    user_id: str,
    *,
    sort: SortKey = "overall",
    profiles: list[Profile] | None = None,
    posts_map: dict[str, list[Post]] | None = None,
) -> list[dict[str, Any]]:
    if profiles is None:
        profiles = await Profile.find(Profile.user_id == user_id).to_list()
    if posts_map is None:
        posts_map = await _posts_by_profile(user_id)

    # Previous ranks from last week's snapshot ordering by followers as proxy
    week_ago = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
    snaps = await ProfileSnapshot.find(
        ProfileSnapshot.user_id == user_id,
        ProfileSnapshot.snapshot_date <= week_ago,
    ).to_list()
    # latest snap per profile on/before week_ago
    latest_prev: dict[str, ProfileSnapshot] = {}
    for s in snaps:
        cur = latest_prev.get(s.profile_id)
        if not cur or s.snapshot_date > cur.snapshot_date:
            latest_prev[s.profile_id] = s
    prev_followers = {pid: s.followers for pid, s in latest_prev.items()}
    prev_order = sorted(prev_followers.items(), key=lambda x: x[1], reverse=True)
    prev_rank = {pid: i + 1 for i, (pid, _) in enumerate(prev_order)}

    rows = [score_profile(p, posts_map.get(str(p.id), [])) for p in profiles]

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
    return rows


async def get_student_dashboard(user_id: str, profile_id: str | None = None) -> dict[str, Any]:
    board = await build_leaderboard(user_id, sort="overall")
    if not board:
        return {"empty": True, "creators": [], "creator": None}

    creator = None
    if profile_id:
        creator = next((r for r in board if r["id"] == profile_id), None)
    if not creator:
        # Prefer highest points as "you" / primary
        creator = board[0]

    # Mark you
    for r in board:
        r["is_you"] = r["id"] == creator["id"]

    # Performance series from snapshots
    snaps = (
        await ProfileSnapshot.find(
            ProfileSnapshot.user_id == user_id,
            ProfileSnapshot.profile_id == creator["id"],
        )
        .sort(+ProfileSnapshot.snapshot_date)
        .to_list()
    )
    performance = [
        {
            "date": s.snapshot_date[-5:] if len(s.snapshot_date) >= 5 else s.snapshot_date,
            "views": s.avg_views,
            "points": 0,
            "followers": s.followers,
        }
        for s in snaps[-14:]
    ]
    if not performance:
        performance = [
            {
                "date": "now",
                "views": creator["avg_views"],
                "points": creator["points"],
                "followers": creator["followers"],
            }
        ]

    followers_delta = 0
    if len(snaps) >= 2:
        followers_delta = snaps[-1].followers - snaps[-2].followers
    elif creator["growth_pct_today"]:
        followers_delta = int(creator["followers"] * (creator["growth_pct_today"] / 100))

    top = [r for r in board if not r.get("is_you")][:5]

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
    }


async def get_admin_overview(user_id: str) -> dict[str, Any]:
    profiles = await Profile.find(Profile.user_id == user_id).to_list()
    posts_map = await _posts_by_profile(user_id)
    board = await build_leaderboard(user_id, sort="overall", profiles=profiles, posts_map=posts_map)
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
    snaps = await ProfileSnapshot.find(
        ProfileSnapshot.user_id == user_id,
        ProfileSnapshot.snapshot_date >= since,
    ).to_list()

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

    updated_today = sum(
        1 for p in profiles if p.last_success_at and p.last_success_at.strftime("%Y-%m-%d") == today
    )
    failed = sum(1 for p in profiles if p.status == ProfileStatus.FAILED)
    private = sum(1 for p in profiles if p.is_private)
    inactive = sum(1 for r in board if r["posts_7d"] == 0)

    grit = {
        "qualified": sum(1 for r in board if r["grit_status"] == "qualified"),
        "striking": sum(1 for r in board if r["grit_status"] == "striking"),
        "at_risk": sum(1 for r in board if r["grit_status"] in {"at_risk", "not_eligible"}),
    }

    # Jobs as submission proxy
    jobs = await Job.find(Job.user_id == user_id).sort(-Job.created_at).limit(200).to_list()
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
        {"label": "Account is private", "count": private},
        {"label": "At-risk / inactive flags", "count": grit["at_risk"]},
    ]

    avg_eng = round(sum(r["engagement"] for r in board) / len(board), 2) if board else 0.0

    last_sync_dt = max((p.last_success_at for p in profiles if p.last_success_at), default=None)

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
        "reels_posted": reels,
        "new_followers": sum(max(0, int(p.followers * (p.growth_pct_today / 100))) for p in profiles),
        "growth_series": growth_series,
        "insights": insights,
        "needing_attention": needing,
        "scrape": {
            "tracked": len(profiles),
            "updated_today": updated_today,
            "failed": failed,
            "last_sync": last_sync_dt.isoformat() if last_sync_dt else None,
            "next_sync": "Daily scrape / on Refresh",
        },
        "grit": grit,
        "submissions": submissions,
        "at_risk_count": grit["at_risk"],
        "leaderboard_preview": board[:8],
    }
