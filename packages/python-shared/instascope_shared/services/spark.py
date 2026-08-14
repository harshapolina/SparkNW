"""SPARK rankings from real scraped Instagram + YouTube metrics.

Overall leaderboard points come from ``spark_points`` (consistency floor,
performance multiplier, audience growth, plus judged/manual categories).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Literal

from instascope_shared.cohort import clamp_scoring_window, snapshot_floor_ymd
from instascope_shared.core.config import get_settings
from instascope_shared.models import (
    DEFAULT_ORG_ID,
    Job,
    JobStatus,
    Post,
    Profile,
    ProfileSnapshot,
    ProfileStatus,
    YouTubeChannel,
    YouTubeSnapshot,
    YouTubeSyncStatus,
    YouTubeVideo,
)
from instascope_shared.services.spark_points import (
    GROWTH_MILESTONES,
    LONG_BANDS,
    PERFORMANCE_CAP,
    SHORT_BANDS,
    compute_points_breakdown,
    growth_points_for_window,
    growth_pts_absolute,
    long_form_points,
    package_leaderboard_row,
    post_performance_pts,
    short_form_points,
)

SortKey = Literal["overall", "points", "followers", "views", "engagement"]

# Re-export scoring constants for older imports / docs
_growth_pts = growth_pts_absolute
_short_pts = short_form_points
_long_pts = long_form_points
_post_performance_pts = post_performance_pts


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


def _is_long_form(media_type: str, caption: str | None) -> bool:
    mt = (media_type or "").lower()
    if mt == "carousel":
        return True
    if mt in {"video", "reel", "clip"} and caption and len(caption) > 280:
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

    key = (profile.username or str(profile.id) or "spark").lower().encode("utf-8")
    return SPARK_CAMPUSES[sum(key) % len(SPARK_CAMPUSES)]


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
    videos: list[YouTubeVideo] | None = None,
    yt_subscribers: int = 0,
    start_followers: int = 0,
    start_yt_subscribers: int = 0,
    include_youtube: bool = True,
) -> int:
    """Raw SPARK points (programme window). Always floors at SPARK_COHORT_START."""
    scored = compute_points_breakdown(
        posts=posts,
        videos=videos or [],
        followers=int(followers or 0),
        yt_subscribers=int(yt_subscribers or 0),
        start_followers=int(start_followers or 0),
        start_yt_subscribers=int(start_yt_subscribers or 0),
        as_of=as_of,
        from_date=from_date,
        include_youtube=include_youtube,
    )
    return int(scored["points"])


def score_profile(
    profile: Profile,
    posts: list[Post],
    *,
    as_of: datetime | None = None,
    from_date: datetime | None = None,
    followers_override: int | None = None,
    growth_pts_override: int | None = None,
    videos: list[YouTubeVideo] | None = None,
    yt_subscribers: int = 0,
    start_followers: int = 0,
    start_yt_subscribers: int = 0,
    include_youtube: bool | None = None,
) -> dict[str, Any]:
    """Compute SPARK points from scraped IG (+ YouTube) metrics."""
    if include_youtube is None:
        include_youtube = True
    return package_leaderboard_row(
        profile,
        posts,
        videos=videos or [],
        as_of=as_of,
        from_date=from_date,
        followers_override=followers_override,
        yt_subscribers=yt_subscribers,
        start_followers=start_followers,
        start_yt_subscribers=start_yt_subscribers,
        growth_pts_override=growth_pts_override,
        include_youtube=include_youtube,
        campus=_campus(profile),
        initials=_initials(profile.full_name or "", profile.username),
    )


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


def _earliest_snap_by_profile(snaps: list[ProfileSnapshot]) -> dict[str, ProfileSnapshot]:
    earliest: dict[str, ProfileSnapshot] = {}
    for s in snaps:
        cur = earliest.get(s.profile_id)
        if not cur or s.snapshot_date < cur.snapshot_date:
            earliest[s.profile_id] = s
    return earliest


def _empty_youtube_metrics() -> dict[str, Any]:
    return {
        "connected": False,
        "channel_id": None,
        "channel_name": None,
        "handle": None,
        "subscribers": None,
        "views": None,
        "likes": None,
        "comments": None,
        "video_count": None,
        "sync_status": None,
        "last_synced_at": None,
        "last_error": None,
        "subscribers_delta": None,
        "views_delta": None,
        "scoring_enabled": True,
    }


async def _youtube_channels_by_profile(profile_ids: list[str]) -> dict[str, YouTubeChannel]:
    if not profile_ids:
        return {}
    rows = await YouTubeChannel.find({"profile_id": {"$in": profile_ids}}).to_list()
    return {r.profile_id: r for r in rows}


async def _youtube_videos_by_profile(profile_ids: list[str]) -> dict[str, list[YouTubeVideo]]:
    by: dict[str, list[YouTubeVideo]] = defaultdict(list)
    if not profile_ids:
        return by
    rows = await YouTubeVideo.find({"profile_id": {"$in": profile_ids}}).to_list()
    for v in rows:
        by[v.profile_id].append(v)
    return by


def _yt_subscribers_at_cutoffs(
    snaps: list[YouTubeSnapshot],
    *,
    start_ymd: str,
    end_ymd: str,
) -> tuple[dict[str, int], dict[str, int]]:
    """Return (subs_at_start, subs_at_end) from YouTube daily snapshots."""
    start_map: dict[str, YouTubeSnapshot] = {}
    end_map: dict[str, YouTubeSnapshot] = {}
    for s in snaps:
        if s.snapshot_date <= start_ymd:
            cur = start_map.get(s.profile_id)
            if not cur or s.snapshot_date > cur.snapshot_date:
                start_map[s.profile_id] = s
        if s.snapshot_date <= end_ymd:
            cur = end_map.get(s.profile_id)
            if not cur or s.snapshot_date > cur.snapshot_date:
                end_map[s.profile_id] = s
    # If no snapshot on/before start, use earliest in window as baseline
    earliest: dict[str, YouTubeSnapshot] = {}
    for s in snaps:
        if start_ymd <= s.snapshot_date <= end_ymd:
            cur = earliest.get(s.profile_id)
            if not cur or s.snapshot_date < cur.snapshot_date:
                earliest[s.profile_id] = s
    for pid, s in earliest.items():
        if pid not in start_map:
            start_map[pid] = s

    def _subs(m: dict[str, YouTubeSnapshot]) -> dict[str, int]:
        out: dict[str, int] = {}
        for pid, snap in m.items():
            if snap.subscribers is not None:
                out[pid] = int(snap.subscribers)
        return out

    return _subs(start_map), _subs(end_map)


async def _latest_youtube_snaps(profile_ids: list[str]) -> dict[str, YouTubeSnapshot]:
    if not profile_ids:
        return {}
    snaps = await YouTubeSnapshot.find({"profile_id": {"$in": profile_ids}}).to_list()
    latest: dict[str, YouTubeSnapshot] = {}
    for s in snaps:
        cur = latest.get(s.profile_id)
        if not cur or s.snapshot_date > cur.snapshot_date:
            latest[s.profile_id] = s
    return latest


async def _prev_youtube_snaps(
    profile_ids: list[str],
    latest: dict[str, YouTubeSnapshot],
) -> dict[str, YouTubeSnapshot]:
    """Previous snapshot before the latest date (for growth deltas)."""
    if not profile_ids or not latest:
        return {}
    snaps = await YouTubeSnapshot.find({"profile_id": {"$in": profile_ids}}).to_list()
    prev: dict[str, YouTubeSnapshot] = {}
    for s in snaps:
        top = latest.get(s.profile_id)
        if not top or s.snapshot_date >= top.snapshot_date:
            continue
        cur = prev.get(s.profile_id)
        if not cur or s.snapshot_date > cur.snapshot_date:
            prev[s.profile_id] = s
    return prev


def _apply_youtube_to_row(
    row: dict[str, Any],
    channel: YouTubeChannel | None,
    snap: YouTubeSnapshot | None = None,
    prev: YouTubeSnapshot | None = None,
) -> None:
    metrics = _empty_youtube_metrics()
    if channel and channel.connected:
        metrics.update(
            {
                "connected": True,
                "channel_id": channel.channel_id,
                "channel_name": channel.channel_name,
                "handle": channel.handle,
                "subscribers": channel.subscriber_count,
                "views": int(channel.view_count or 0),
                "video_count": int(channel.video_count or 0),
                "likes": int(snap.likes) if snap else None,
                "comments": int(snap.comments) if snap else None,
                "sync_status": channel.sync_status.value
                if hasattr(channel.sync_status, "value")
                else str(channel.sync_status),
                "last_synced_at": channel.last_synced_at.isoformat() if channel.last_synced_at else None,
                "last_error": channel.last_error,
            }
        )
        if snap and prev:
            if snap.subscribers is not None and prev.subscribers is not None:
                metrics["subscribers_delta"] = int(snap.subscribers) - int(prev.subscribers)
            metrics["views_delta"] = int(snap.total_views or 0) - int(prev.total_views or 0)
    row["youtube"] = metrics
    row["youtube_connected"] = metrics["connected"]
    row["youtube_channel_id"] = metrics["channel_id"]
    row["youtube_subscribers"] = metrics["subscribers"]
    row["youtube_views"] = metrics["views"]
    row["youtube_likes"] = metrics["likes"]
    row["youtube_comments"] = metrics["comments"]
    row["youtube_video_count"] = metrics["video_count"]
    # Display metrics; points already include YT via spark_points when scored.
    row["scoring_includes_youtube"] = True


async def _enrich_leaderboard_youtube(rows: list[dict[str, Any]]) -> None:
    ids = [r["id"] for r in rows]
    channels = await _youtube_channels_by_profile(ids)
    snaps = await _latest_youtube_snaps(ids)
    for r in rows:
        pid = r["id"]
        _apply_youtube_to_row(r, channels.get(pid), snaps.get(pid))


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

    # Always score inside the SPARK cohort window (floored at programme start).
    window_start, window_end = clamp_scoring_window(from_date, to_date)

    # Previous ranks: snapshot on/before window start (followers proxy).
    prev_cutoff = window_start.strftime("%Y-%m-%d")
    end_cutoff = window_end.strftime("%Y-%m-%d")

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
    followers_at_start: dict[str, int] = {pid: int(f or 0) for pid, f in prev_followers.items()}
    if profile_ids:
        end_snaps = await ProfileSnapshot.find(
            {"profile_id": {"$in": profile_ids}, "snapshot_date": {"$lte": end_cutoff}}
        ).to_list()
        for pid, snap in _latest_snap_by_profile(end_snaps).items():
            followers_at_end[pid] = int(snap.followers or 0)

        # No Jul-15 snapshot → use first scrape inside the window as baseline
        # (otherwise start=0 awards every growth milestone unfairly).
        missing = [pid for pid in profile_ids if pid not in followers_at_start]
        if missing:
            window_snaps = await ProfileSnapshot.find(
                {
                    "profile_id": {"$in": missing},
                    "snapshot_date": {"$gte": prev_cutoff, "$lte": end_cutoff},
                }
            ).to_list()
            for pid, snap in _earliest_snap_by_profile(window_snaps).items():
                followers_at_start[pid] = int(snap.followers or 0)

    # YouTube videos + subscriber baselines for overall SPARK points
    videos_map = await _youtube_videos_by_profile(profile_ids)
    channels = await _youtube_channels_by_profile(profile_ids)
    yt_snaps_all = (
        await YouTubeSnapshot.find({"profile_id": {"$in": profile_ids}}).to_list()
        if profile_ids
        else []
    )
    yt_start, yt_end = _yt_subscribers_at_cutoffs(
        yt_snaps_all, start_ymd=prev_cutoff, end_ymd=end_cutoff
    )
    for pid, ch in channels.items():
        if pid not in yt_end and ch.subscriber_count is not None:
            yt_end[pid] = int(ch.subscriber_count)
        if pid not in yt_start and ch.subscriber_count is not None:
            # No history → baseline = current (no unearned growth milestones)
            yt_start[pid] = int(ch.subscriber_count)

    rows: list[dict[str, Any]] = []
    include_yt = bool(get_settings().youtube_scoring_enabled)
    for p in profiles:
        pid = str(p.id)
        end_fol = followers_at_end.get(pid)
        start_fol = int(followers_at_start.get(pid, 0) or 0)
        end_ig = int(end_fol if end_fol is not None else (p.followers or 0))
        end_yt = int(yt_end.get(pid, 0) or 0) if include_yt else 0
        start_yt = int(yt_start.get(pid, 0) or 0) if include_yt else 0
        growth_override = growth_points_for_window(
            end_ig=end_ig,
            end_yt=end_yt,
            start_ig=start_fol,
            start_yt=start_yt,
        )
        rows.append(
            score_profile(
                p,
                posts_map.get(pid, []),
                from_date=window_start,
                as_of=window_end,
                followers_override=end_ig,
                growth_pts_override=growth_override,
                videos=videos_map.get(pid, []) if include_yt else [],
                yt_subscribers=end_yt,
                start_followers=start_fol,
                start_yt_subscribers=start_yt,
                include_youtube=include_yt,
            )
        )

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
        r["window_from"] = window_start.strftime("%Y-%m-%d")
        r["window_to"] = window_end.strftime("%Y-%m-%d")
    await _enrich_leaderboard_youtube(rows)
    return rows


async def get_top_10(org_id: str | None = None) -> dict[str, Any]:
    start, end = clamp_scoring_window(None, None)
    board = await build_leaderboard(
        org_id, sort="overall", from_date=start, to_date=end
    )
    return {
        "items": board[:10],
        "total_creators": len(board),
        "week_label": f"LIVE • {datetime.utcnow().strftime('%d %b %Y')}",
        "from_date": start.strftime("%Y-%m-%d"),
        "to_date": end.strftime("%Y-%m-%d"),
    }


async def get_student_dashboard(org_id: str, profile_id: str) -> dict[str, Any]:
    start, end = clamp_scoring_window(None, None)
    board = await build_leaderboard(
        org_id,
        sort="overall",
        you_profile_id=profile_id,
        from_date=start,
        to_date=end,
    )
    if not board:
        return {"empty": True, "creators": [], "creator": None}

    creator = next((r for r in board if r["id"] == profile_id), None)
    if not creator:
        return {"empty": True, "creators": [], "creator": None, "error": "Profile not on leaderboard"}

    profile = await Profile.get(profile_id)
    from instascope_shared.instagram_time import infer_posted_at

    window_start, window_end = clamp_scoring_window(start, end)
    start_n = _naive_dt(window_start) or window_start
    end_n = _naive_dt(window_end) or window_end
    all_posts = await Post.find(Post.profile_id == profile_id).sort(-Post.posted_at).to_list()
    posts: list[Post] = []
    for p in all_posts:
        dt = _naive_dt(p.posted_at)
        if dt is None:
            inferred = infer_posted_at(
                shortcode=p.shortcode,
                ig_post_id=getattr(p, "ig_post_id", None),
            )
            dt = _naive_dt(inferred)
            if dt is not None:
                p.posted_at = dt
        if dt is None:
            continue
        if start_n <= dt <= end_n:
            posts.append(p)

    # Performance series from snapshots (programme floor → today)
    floor_ymd = snapshot_floor_ymd()
    snaps = (
        await ProfileSnapshot.find(
            ProfileSnapshot.profile_id == creator["id"],
            ProfileSnapshot.snapshot_date >= floor_ymd,
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

    yt_channel = await YouTubeChannel.find_one(YouTubeChannel.profile_id == profile_id)
    yt_snaps = await _latest_youtube_snaps([profile_id])
    yt_prev = await _prev_youtube_snaps([profile_id], yt_snaps)
    youtube_row: dict[str, Any] = {"id": profile_id}
    _apply_youtube_to_row(
        youtube_row,
        yt_channel,
        yt_snaps.get(profile_id),
        yt_prev.get(profile_id),
    )
    youtube_payload = youtube_row.get("youtube") or _empty_youtube_metrics()

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
        "youtube": youtube_payload,
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
    window_start, window_end = clamp_scoring_window(None, None)
    board = await build_leaderboard(
        oid,
        sort="overall",
        profiles=profiles,
        posts_map=posts_map,
        from_date=window_start,
        to_date=window_end,
    )
    # Flatten posts once — keep only cohort-window posts for overview charts/totals.
    all_posts = [p for bucket in posts_map.values() for p in bucket]
    posts = [
        p
        for p in all_posts
        if p.posted_at
        and _naive_dt(p.posted_at) is not None
        and _naive_dt(p.posted_at) >= window_start
        and _naive_dt(p.posted_at) <= window_end
    ]
    today = window_end.strftime("%Y-%m-%d")
    since = window_start.strftime("%Y-%m-%d")

    total_followers = sum(int(r["followers"]) for r in board) if board else sum(p.followers for p in profiles)
    total_views = sum(int(r["views"]) for r in board)
    total_likes = sum(int(r["likes"]) for r in board)
    total_comments = sum(int(r["comments"]) for r in board)
    total_points = sum(int(r["points"]) for r in board)
    reels = sum(1 for p in posts if str(getattr(p.media_type, "value", p.media_type)).lower() == "reel")

    # Fast WoW: points added in the last 7 days (new post performance + consistency + growth milestone deltas)
    week_ago_dt = max(window_start, datetime.utcnow() - timedelta(days=7))
    week_ago_str = week_ago_dt.strftime("%Y-%m-%d")

    week_perf = 0
    for p in posts:
        posted = p.posted_at
        if not posted:
            continue
        if posted.replace(tzinfo=None) >= week_ago_dt:
            week_perf += _post_performance_pts(p)[0]

    week_cons = sum(int((r.get("points_breakdown") or {}).get("consistency") or 0) for r in board)

    # Reuse snaps from cohort start for growth series + WoW growth deltas
    since = snapshot_floor_ymd()
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

    # Mutually exclusive status buckets (must sum to len(profiles)).
    # Priority: unavailable → failed → paused → scraped (public|private) → pending.
    scraped_public = 0
    scraped_private = 0
    failed = 0
    unavailable = 0
    paused = 0
    pending = 0
    private = 0
    for p in profiles:
        if p.is_private:
            private += 1
        if p.status == ProfileStatus.UNAVAILABLE:
            unavailable += 1
        elif p.status == ProfileStatus.FAILED:
            failed += 1
        elif p.status == ProfileStatus.PAUSED:
            paused += 1
        elif _has_ig_card(p):
            if p.is_private:
                scraped_private += 1
            else:
                scraped_public += 1
        else:
            pending += 1

    scraped_successfully = scraped_public + scraped_private
    private_scraped = scraped_private
    private_pending = sum(
        1
        for p in profiles
        if p.is_private
        and not _has_ig_card(p)
        and p.status
        not in {ProfileStatus.FAILED, ProfileStatus.UNAVAILABLE, ProfileStatus.PAUSED}
    )

    updated_today = sum(1 for p in profiles if _date_str(p.last_success_at) == today)
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
                    "category": "operations",
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
                    "category": "operations",
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
                    "category": "growth_anomaly",
                    "severity": "medium",
                    "title": f"@{p.username} {'grew' if g > 0 else 'dropped'} {g:+.2f}%",
                    "body": f"Follower change vs previous scrape · {int(p.followers):,} followers now.",
                    "profile_id": str(p.id),
                    "username": p.username,
                    "created_at": (p.last_success_at or p.updated_at or datetime.utcnow()).isoformat(),
                }
            )
    alerts.sort(key=lambda a: a["created_at"], reverse=True)

    # YouTube portfolio summary (separate from Instagram scrape health)
    yt_channels = await YouTubeChannel.find(
        {"profile_id": {"$in": profile_ids}} if profile_ids else {}
    ).to_list() if profile_ids else []
    from instascope_shared.services.spark_alerts import build_integrity_alerts

    integrity = await build_integrity_alerts(profiles, yt_channels)
    alerts = integrity + alerts
    alerts = alerts[:120]

    from instascope_shared.services.app_config import is_daily_youtube_sync_enabled

    yt_connected = [c for c in yt_channels if c.connected]
    yt_failed = [
        c
        for c in yt_channels
        if c.sync_status
        in {YouTubeSyncStatus.FAILED, YouTubeSyncStatus.UNAVAILABLE, YouTubeSyncStatus.QUOTA_EXCEEDED}
    ]
    yt_scraped = [
        c
        for c in yt_connected
        if c.last_synced_at and c.sync_status == YouTubeSyncStatus.SUCCESS
    ]
    yt_pending = [
        c
        for c in yt_connected
        if not c.last_synced_at or c.sync_status == YouTubeSyncStatus.PENDING
    ]
    yt_last = None
    for c in yt_channels:
        if c.last_synced_at and (yt_last is None or c.last_synced_at > yt_last):
            yt_last = c.last_synced_at

    profiles_by_id = {str(p.id): p for p in profiles}
    top_channels = []
    for c in sorted(
        yt_connected,
        key=lambda x: int(x.subscriber_count or 0),
        reverse=True,
    )[:8]:
        p = profiles_by_id.get(c.profile_id)
        student = getattr(p, "student", None) or {}
        top_channels.append(
            {
                "profile_id": c.profile_id,
                "username": getattr(p, "username", None) or "—",
                "full_name": getattr(p, "full_name", None)
                or (student.get("full_name") if isinstance(student, dict) else None),
                "student_id": student.get("student_id") if isinstance(student, dict) else None,
                "campus": student.get("university") if isinstance(student, dict) else None,
                "channel_name": c.channel_name,
                "handle": c.handle,
                "subscribers": int(c.subscriber_count or 0),
                "hidden_subscribers": bool(c.hidden_subscriber_count),
                "views": int(c.view_count or 0),
                "videos": int(c.video_count or 0),
                "sync_status": c.sync_status.value
                if hasattr(c.sync_status, "value")
                else str(c.sync_status),
                "last_synced_at": c.last_synced_at.isoformat() + "Z"
                if c.last_synced_at
                else None,
            }
        )

    from instascope_shared.services.youtube_jobs import youtube_ref_from_student

    connected_pids = {c.profile_id for c in yt_connected}
    yt_no_link = 0
    for p in profiles:
        if str(p.id) in connected_pids:
            continue
        student = getattr(p, "student", None) or {}
        if not youtube_ref_from_student(student if isinstance(student, dict) else None):
            yt_no_link += 1

    youtube_overview = {
        "connected": len(yt_connected),
        "total_channels": len(yt_channels),
        "scraped": len(yt_scraped),
        "not_scraped": max(0, len(yt_connected) - len(yt_scraped)),
        "pending_sync": len(yt_pending),
        "no_youtube": yt_no_link,
        "total_subscribers": sum(int(c.subscriber_count or 0) for c in yt_connected),
        "total_views": sum(int(c.view_count or 0) for c in yt_connected),
        "total_videos": sum(int(c.video_count or 0) for c in yt_connected),
        "avg_subscribers": (
            round(
                sum(int(c.subscriber_count or 0) for c in yt_connected) / len(yt_connected),
                1,
            )
            if yt_connected
            else 0.0
        ),
        "failed": len(yt_failed),
        "quota_exceeded": sum(
            1 for c in yt_channels if c.sync_status == YouTubeSyncStatus.QUOTA_EXCEEDED
        ),
        "last_sync": yt_last.isoformat() if yt_last else None,
        "next_sync": "Daily 08:00 IST when YouTube sync is enabled",
        "daily_sync_enabled": await is_daily_youtube_sync_enabled(),
        "scoring_enabled": bool(get_settings().youtube_scoring_enabled),
        "top_channels": top_channels,
    }

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
        "youtube": youtube_overview,
        # Lifetime unique counts (1 profile = 1 count; re-scrapes do not inflate).
        "overall": {
            "total_profiles": len(profiles),
            "scraped_successfully": scraped_successfully,
            "scraped_public": scraped_public,
            "scraped_private": scraped_private,
            "failed": failed,
            "unavailable": unavailable,
            "paused": paused,
            "pending": pending,
            "private": private,
            "private_scraped": private_scraped,
            "private_pending": private_pending,
            # Exclusive status math: scraped + failed + unavailable + paused + pending == total
            "status_sum": scraped_successfully + failed + unavailable + paused + pending,
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
