"""Profile CRUD, bulk ops, status transitions."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import HTTPException, status

from instascope_shared.domain.instagram import extract_username, profile_url_for
from instascope_shared.models import Job, JobStatus, JobType, Profile, ProfileStatus
from instascope_shared.schemas import AddProfileRequest, ProfileListResponse, ProfileResponse


def to_profile_response(p: Profile) -> ProfileResponse:
    return ProfileResponse(
        id=str(p.id),
        username=p.username,
        full_name=p.full_name,
        bio=p.bio,
        website=p.website,
        avatar_url=p.avatar_url,
        is_verified=p.is_verified,
        profile_url=p.profile_url,
        followers=p.followers,
        following=p.following,
        posts_count=p.posts_count,
        avg_likes=p.avg_likes,
        avg_views=p.avg_views,
        avg_comments=p.avg_comments,
        engagement_rate=p.engagement_rate,
        growth_pct_today=p.growth_pct_today,
        is_private=bool(getattr(p, "is_private", False)),
        is_business=bool(getattr(p, "is_business", False)),
        category=getattr(p, "category", None),
        highlight_reel_count=int(getattr(p, "highlight_reel_count", 0) or 0),
        follower_following_ratio=float(getattr(p, "follower_following_ratio", 0.0) or 0.0),
        insights=dict(getattr(p, "insights", None) or {}),
        status=p.status.value if hasattr(p.status, "value") else str(p.status),
        last_scraped_at=p.last_scraped_at,
        last_success_at=p.last_success_at,
        last_error=p.last_error,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


async def add_profile(user_id: str, payload: AddProfileRequest) -> Profile:
    try:
        username = extract_username(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    existing = await Profile.find_one(Profile.user_id == user_id, Profile.username == username)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Profile already tracked")

    profile = Profile(
        user_id=user_id,
        username=username,
        profile_url=profile_url_for(username),
        status=ProfileStatus.ACTIVE,
    )
    await profile.insert()
    return profile


async def list_profiles(
    user_id: str,
    *,
    q: Optional[str] = None,
    status_filter: Optional[str] = None,
    sort_by: str = "updated_at",
    sort_dir: str = "desc",
    page: int = 1,
    page_size: int = 20,
) -> ProfileListResponse:
    query = Profile.find(Profile.user_id == user_id)

    # Beanie FindMany — filter in Python for q/status when needed for simplicity at day-1;
    # for 1M scale, push filters into Mongo queries.
    profiles = await query.to_list()

    if q:
        ql = q.lower()
        profiles = [p for p in profiles if ql in p.username.lower() or (p.full_name and ql in p.full_name.lower())]

    if status_filter:
        profiles = [p for p in profiles if str(p.status.value if hasattr(p.status, "value") else p.status) == status_filter]

    reverse = sort_dir != "asc"
    sort_key_map = {
        "username": lambda p: p.username.lower(),
        "followers": lambda p: p.followers,
        "following": lambda p: p.following,
        "posts": lambda p: p.posts_count,
        "avg_likes": lambda p: p.avg_likes,
        "avg_views": lambda p: p.avg_views,
        "growth": lambda p: p.growth_pct_today,
        "updated_at": lambda p: p.updated_at or p.created_at,
        "last_updated": lambda p: p.last_scraped_at or p.created_at,
    }
    key_fn = sort_key_map.get(sort_by, sort_key_map["updated_at"])
    profiles.sort(key=key_fn, reverse=reverse)

    total = len(profiles)
    start = max(page - 1, 0) * page_size
    page_items = profiles[start : start + page_size]

    return ProfileListResponse(
        items=[to_profile_response(p) for p in page_items],
        total=total,
        page=page,
        page_size=page_size,
    )


async def get_profile(user_id: str, profile_id: str) -> Profile:
    profile = await Profile.get(profile_id)
    if not profile or profile.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return profile


async def delete_profiles(user_id: str, ids: list[str]) -> int:
    count = 0
    for pid in ids:
        profile = await Profile.get(pid)
        if profile and profile.user_id == user_id:
            await profile.delete()
            count += 1
    return count


async def set_profiles_status(user_id: str, ids: list[str], status_value: ProfileStatus) -> int:
    count = 0
    for pid in ids:
        profile = await Profile.get(pid)
        if profile and profile.user_id == user_id:
            profile.status = status_value
            profile.updated_at = datetime.utcnow()
            await profile.save()
            count += 1
    return count


async def enqueue_refresh(user_id: str, ids: list[str], *, priority: int = 1) -> list[Job]:
    """Create pending scrape jobs. API layer dispatches to Celery separately."""
    jobs: list[Job] = []
    for pid in ids:
        profile = await Profile.get(pid)
        if not profile or profile.user_id != user_id:
            continue
        job = Job(
            user_id=user_id,
            profile_id=str(profile.id),
            job_type=JobType.SCRAPE_PROFILE,
            status=JobStatus.PENDING,
            priority=priority,
        )
        await job.insert()
        jobs.append(job)
    return jobs
