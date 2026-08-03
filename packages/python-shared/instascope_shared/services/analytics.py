"""Overview + profile analytics from snapshots and posts."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any

from instascope_shared.models import Post, Profile, ProfileSnapshot, ProfileStatus
from instascope_shared.schemas import (
    NamedValue,
    OverviewCharts,
    OverviewResponse,
    OverviewStats,
    ProfileAnalyticsResponse,
    SeriesPoint,
)
from instascope_shared.services.profiles import to_profile_response


def _today() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


async def get_overview(user_id: str) -> OverviewResponse:
    profiles = await Profile.find(Profile.user_id == user_id).to_list()
    today = _today()

    total = len(profiles)
    updated_today = sum(
        1
        for p in profiles
        if p.last_success_at and p.last_success_at.strftime("%Y-%m-%d") == today
    )
    failed = sum(1 for p in profiles if p.status == ProfileStatus.FAILED)

    def avg(attr: str) -> float:
        if not profiles:
            return 0.0
        return round(sum(getattr(p, attr) for p in profiles) / len(profiles), 2)

    growth_today = sum(int(p.followers * (p.growth_pct_today / 100)) for p in profiles if p.growth_pct_today)

    # Snapshots for last 30 days (user-scoped)
    since = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
    snapshots = await ProfileSnapshot.find(
        ProfileSnapshot.user_id == user_id,
        ProfileSnapshot.snapshot_date >= since,
    ).to_list()

    by_date_followers: dict[str, list[int]] = defaultdict(list)
    for s in snapshots:
        by_date_followers[s.snapshot_date].append(s.followers)

    followers_over_time = [
        SeriesPoint(date=d, value=round(sum(vals) / len(vals), 2))
        for d, vals in sorted(by_date_followers.items())
    ]

    posts = await Post.find(Post.user_id == user_id).to_list()
    posts_by_day: Counter[str] = Counter()
    types: Counter[str] = Counter()
    heatmap: dict[tuple[int, int], int] = defaultdict(int)

    for post in posts:
        if post.posted_at:
            posts_by_day[post.posted_at.strftime("%Y-%m-%d")] += 1
            heatmap[(post.posted_at.weekday(), post.posted_at.hour)] += 1
        types[str(post.media_type.value if hasattr(post.media_type, "value") else post.media_type)] += 1

    posts_per_day = [
        SeriesPoint(date=d, value=float(c))
        for d, c in sorted(posts_by_day.items())[-30:]
    ]
    content_types = [NamedValue(name=k, value=float(v)) for k, v in types.items()]
    posting_heatmap = [
        {"day": d, "hour": h, "count": c} for (d, h), c in heatmap.items()
    ]

    recent = sorted(profiles, key=lambda p: p.updated_at, reverse=True)[:8]

    return OverviewResponse(
        stats=OverviewStats(
            total_profiles=total,
            profiles_updated_today=updated_today,
            failed_updates=failed,
            average_engagement=avg("engagement_rate"),
            average_followers=avg("followers"),
            average_views=avg("avg_views"),
            average_likes=avg("avg_likes"),
            follower_growth_today=growth_today,
        ),
        charts=OverviewCharts(
            followers_over_time=followers_over_time,
            posts_per_day=posts_per_day,
            content_types=content_types,
            posting_heatmap=posting_heatmap,
        ),
        recent_updates=[to_profile_response(p) for p in recent],
    )


async def get_profile_analytics(user_id: str, profile_id: str) -> ProfileAnalyticsResponse:
    snapshots = await ProfileSnapshot.find(
        ProfileSnapshot.user_id == user_id,
        ProfileSnapshot.profile_id == profile_id,
    ).sort(+ProfileSnapshot.snapshot_date).to_list()

    posts = await Post.find(Post.profile_id == profile_id).to_list()

    followers_trend = [SeriesPoint(date=s.snapshot_date, value=float(s.followers)) for s in snapshots]
    views_trend = [SeriesPoint(date=s.snapshot_date, value=s.avg_views) for s in snapshots]
    likes_trend = [SeriesPoint(date=s.snapshot_date, value=s.avg_likes) for s in snapshots]
    comments_trend = [SeriesPoint(date=s.snapshot_date, value=s.avg_comments) for s in snapshots]

    day_counts: Counter[str] = Counter()
    hour_counts: Counter[int] = Counter()
    for post in posts:
        if post.posted_at:
            day_counts[post.posted_at.strftime("%A")] += 1
            hour_counts[post.posted_at.hour] += 1

    best_day = day_counts.most_common(1)[0][0] if day_counts else None
    best_hour = hour_counts.most_common(1)[0][0] if hour_counts else None

    growth = snapshots[-1].followers_growth_pct if snapshots else 0.0
    avg_eng = snapshots[-1].engagement_rate if snapshots else 0.0

    # posts per week approx
    if posts:
        dated = [p for p in posts if p.posted_at]
        if len(dated) >= 2:
            span_days = max((max(p.posted_at for p in dated) - min(p.posted_at for p in dated)).days, 1)
            posting_frequency = round(len(dated) / (span_days / 7), 2)
        else:
            posting_frequency = float(len(dated))
    else:
        posting_frequency = 0.0

    return ProfileAnalyticsResponse(
        followers_trend=followers_trend,
        views_trend=views_trend,
        likes_trend=likes_trend,
        comments_trend=comments_trend,
        posting_frequency=posting_frequency,
        average_engagement=avg_eng,
        best_posting_day=best_day,
        best_posting_hour=best_hour,
        growth_pct=growth,
    )
