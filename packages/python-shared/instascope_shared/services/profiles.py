"""Profile CRUD, bulk ops, status transitions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, status

from instascope_shared.analytics.metrics import compute_post_metrics
from instascope_shared.cohort import clamp_scoring_window, cohort_start_ymd
from instascope_shared.domain.instagram import extract_username, profile_url_for
from instascope_shared.instagram_time import infer_posted_at
from instascope_shared.models import (
    DEFAULT_ORG_ID,
    Job,
    JobStatus,
    JobType,
    Post,
    Profile,
    ProfileSnapshot,
    ProfileStatus,
)
from instascope_shared.schemas import AddProfileRequest, ProfileListResponse, ProfileResponse, UpdateProfileRequest
from instascope_shared.services.scrape_pipeline import heal_soft_scrape_failure
from instascope_shared.services.student_roster import merge_student


def _programme_posts_from_insights(insights: dict | None) -> int | None:
    """Return programme-window post count from stored insights, or None if unknown."""
    if not isinstance(insights, dict) or not insights:
        return None
    if "sampled_posts" in insights:
        try:
            return max(0, int(insights.get("sampled_posts") or 0))
        except (TypeError, ValueError):
            return 0
    if "posts_in_window" in insights:
        try:
            return max(0, int(insights.get("posts_in_window") or 0))
        except (TypeError, ValueError):
            return 0
    return None


def _apply_follower_baseline(
    resp: ProfileResponse,
    *,
    baseline_followers: int | None,
    baseline_date: str | None,
) -> ProfileResponse:
    """Attach gain since first programme-window scrape (no IG backfill)."""
    if baseline_followers is None or not baseline_date:
        resp.followers_baseline = None
        resp.followers_baseline_date = None
        resp.followers_gained = 0
        resp.followers_gained_pct = 0.0
        return resp
    current = int(resp.followers or 0)
    base = max(0, int(baseline_followers))
    gained = current - base
    if base > 0:
        pct = round((gained / base) * 100, 2)
    elif current > 0:
        pct = 100.0
    else:
        pct = 0.0
    resp.followers_baseline = base
    resp.followers_baseline_date = baseline_date
    resp.followers_gained = gained
    resp.followers_gained_pct = pct
    return resp


async def _earliest_baselines(
    profile_ids: list[str],
) -> dict[str, tuple[str, int]]:
    """Earliest snapshot on/after programme start → (snapshot_date, followers)."""
    out: dict[str, tuple[str, int]] = {}
    if not profile_ids:
        return out
    floor = cohort_start_ymd()
    _, window_end = clamp_scoring_window()
    end = window_end.strftime("%Y-%m-%d")
    snaps = await ProfileSnapshot.find(
        {
            "profile_id": {"$in": profile_ids},
            "snapshot_date": {"$gte": floor, "$lte": end},
        }
    ).to_list()
    for s in snaps:
        pid = str(s.profile_id)
        cur = out.get(pid)
        if cur is None or s.snapshot_date < cur[0]:
            out[pid] = (s.snapshot_date, int(s.followers or 0))
    return out


def to_profile_response(p: Profile) -> ProfileResponse:
    student = dict(getattr(p, "student", None) or {})
    student.setdefault("youtube_status", "Coming soon")
    insights = dict(getattr(p, "insights", None) or {})
    # List board overwrites with a live programme-window count. Do not seed from
    # stale lifetime ``sampled_posts`` here — that made 0-in-window look like 36.
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
        programme_posts=0,
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
        insights=insights,
        student=student,
        scrape_progress=dict(getattr(p, "scrape_progress", None) or {}) or None,
        youtube_channel_id=getattr(p, "youtube_channel_id", None),
        youtube_connected=bool(getattr(p, "youtube_connected", False)),
        youtube_last_synced_at=getattr(p, "youtube_last_synced_at", None),
        status=p.status.value if hasattr(p.status, "value") else str(p.status),
        last_scraped_at=p.last_scraped_at,
        last_success_at=p.last_success_at,
        last_error=p.last_error,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


def _post_to_metrics_dict(p: Post) -> dict:
    """Shape a Post for compute_post_metrics (must include ids for date recovery)."""
    media = p.media_type.value if hasattr(p.media_type, "value") else str(p.media_type)
    media_l = str(media or "").lower()
    return {
        "likes": p.likes,
        "comments": p.comments,
        "views": p.views,
        "caption": p.caption,
        "media_type": media,
        "is_video": media_l in {"reel", "video", "clips", "graphvideo"},
        "shortcode": p.shortcode,
        "ig_post_id": getattr(p, "ig_post_id", None) or None,
        "id": getattr(p, "ig_post_id", None) or None,
        "posted_at": p.posted_at,
    }


async def to_profile_response_cohort(p: Profile) -> ProfileResponse:
    """Profile payload with Insights / averages recomputed from programme-window posts only."""
    resp = to_profile_response(p)
    posts = await Post.find(Post.profile_id == str(p.id)).to_list()
    posts_data = [_post_to_metrics_dict(x) for x in posts]
    metrics = compute_post_metrics(
        posts_data, followers=int(p.followers or 0), programme_window=True
    )
    # Prefer live cohort metrics over lifetime scrape blob stored on the profile.
    # Always overwrite averages — including zeros when the programme window is empty —
    # so header stats never stay stale vs Insights cards.
    resp.insights = metrics
    resp.programme_posts = int(metrics.get("sampled_posts") or metrics.get("posts_in_window") or 0)
    resp.avg_likes = float(metrics.get("avg_likes") or 0)
    resp.avg_views = float(metrics.get("avg_views") or 0)
    resp.avg_comments = float(metrics.get("avg_comments") or 0)
    resp.engagement_rate = float(metrics.get("engagement_rate") or 0)
    baselines = await _earliest_baselines([str(p.id)])
    base = baselines.get(str(p.id))
    if base:
        _apply_follower_baseline(resp, baseline_followers=base[1], baseline_date=base[0])
    return resp


async def _live_programme_post_counts(profile_ids: list[str]) -> dict[str, int]:
    """Count posts inside the programme window (batch, for list board).

    Matches Insights: missing posted_at is recovered from shortcode/media id.
    Profiles with no in-window posts are explicitly 0 (never fall back to stale
    lifetime ``insights.sampled_posts``).
    """
    out: dict[str, int] = {pid: 0 for pid in profile_ids}
    if not profile_ids:
        return out
    start, end = clamp_scoring_window()
    start_n = start.replace(tzinfo=None) if getattr(start, "tzinfo", None) else start
    end_n = end.replace(tzinfo=None) if getattr(end, "tzinfo", None) else end

    posts = await Post.find({"profile_id": {"$in": profile_ids}}).to_list()
    for p in posts:
        pid = str(p.profile_id)
        if pid not in out:
            continue
        try:
            dt = p.posted_at
            if dt is None:
                dt = infer_posted_at(
                    shortcode=p.shortcode,
                    ig_post_id=getattr(p, "ig_post_id", None),
                )
            if dt is None:
                continue
            if getattr(dt, "tzinfo", None) is not None:
                dt_n = dt.astimezone(timezone.utc).replace(tzinfo=None)
            else:
                dt_n = dt
            if start_n <= dt_n <= end_n:
                out[pid] = out.get(pid, 0) + 1
        except Exception:
            continue
    return out


async def list_posts_in_programme_window(profile_id: str) -> list[Post]:
    """Posts tab: only rows with recoverable posted_at inside programme window."""
    start, end = clamp_scoring_window()
    posts = await Post.find(Post.profile_id == profile_id).sort(-Post.posted_at).to_list()
    start_n = start.replace(tzinfo=None) if getattr(start, "tzinfo", None) else start
    end_n = end.replace(tzinfo=None) if getattr(end, "tzinfo", None) else end
    out: list[Post] = []
    for p in posts:
        try:
            dt = p.posted_at
            if dt is None:
                dt = infer_posted_at(shortcode=p.shortcode, ig_post_id=getattr(p, "ig_post_id", None))
            if dt is None:
                continue
            if getattr(dt, "tzinfo", None) is not None:
                dt_n = dt.astimezone(timezone.utc).replace(tzinfo=None)
            else:
                dt_n = dt
            if start_n <= dt_n <= end_n:
                if p.posted_at is None:
                    p.posted_at = dt_n
                out.append(p)
        except Exception:
            continue
    out.sort(key=lambda x: x.posted_at or datetime.min, reverse=True)
    return out


async def add_profile(user_id: str, payload: AddProfileRequest, *, upsert_student: bool = False) -> Profile:
    try:
        username = extract_username(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    existing = await Profile.find_one(Profile.user_id == user_id, Profile.username == username)
    student = merge_student(None, getattr(payload, "student", None) or {})
    if existing:
        if upsert_student:
            if student:
                existing.student = merge_student(getattr(existing, "student", None), student)
                if not getattr(existing, "org_id", None):
                    existing.org_id = DEFAULT_ORG_ID
                existing.updated_at = datetime.utcnow()
                await existing.save()
            return existing
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Profile already tracked")

    profile = Profile(
        user_id=user_id,
        org_id=DEFAULT_ORG_ID,
        username=username,
        profile_url=profile_url_for(username),
        status=ProfileStatus.ACTIVE,
        student=student,
    )
    await profile.insert()
    return profile


async def update_profile_instagram(user_id: str, profile_id: str, payload: UpdateProfileRequest) -> Profile:
    """Update tracked Instagram username/URL. Same profile id — Refresh then scrapes the new handle."""
    profile = await get_profile(user_id, profile_id)
    try:
        username = extract_username(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if username == (profile.username or "").lower():
        # Normalize profile_url even on no-op rename
        desired_url = profile_url_for(username)
        if profile.profile_url != desired_url:
            profile.profile_url = desired_url
            profile.updated_at = datetime.utcnow()
            await profile.save()
        return profile

    clash = await Profile.find_one(Profile.user_id == user_id, Profile.username == username)
    if clash and str(clash.id) != str(profile.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"@{username} is already tracked on another profile",
        )

    profile.username = username
    profile.profile_url = profile_url_for(username)

    # Keep roster IG fields in sync so Student tab / login matching stay consistent.
    student = dict(getattr(profile, "student", None) or {})
    student["instagram_username"] = username
    student["instagram_handle"] = f"@{username}"
    student["instagram_url"] = profile.profile_url
    profile.student = student

    # Wrong-handle "missing" state should not stick after a correction.
    if profile.status == ProfileStatus.UNAVAILABLE:
        profile.status = ProfileStatus.ACTIVE
    profile.last_error = None
    profile.updated_at = datetime.utcnow()
    await profile.save()
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
    filt: dict = {"user_id": user_id}
    if status_filter:
        key = status_filter.strip().lower()
        # Private is a flag, not ProfileStatus. Active = trackable public only
        # (excludes private so the two filters never overlap).
        if key == "private":
            filt["is_private"] = True
        elif key == "active":
            filt["status"] = "active"
            filt["is_private"] = False
        else:
            filt["status"] = status_filter
    q_raw = (q or "").strip()
    if q_raw:
        rx = {"$regex": q_raw, "$options": "i"}
        filt["$or"] = [
            {"username": rx},
            {"full_name": rx},
            {"student.full_name": rx},
            {"student.student_id": rx},
            {"student.university": rx},
            {"student.email": rx},
        ]

    sort_field_map = {
        "username": "username",
        "followers": "followers",
        "following": "following",
        "posts": "posts_count",
        "avg_likes": "avg_likes",
        "avg_views": "avg_views",
        "growth": "growth_pct_today",
        "updated_at": "updated_at",
        "last_updated": "last_scraped_at",
    }
    sort_field = sort_field_map.get(sort_by, "updated_at")
    direction = 1 if sort_dir == "asc" else -1

    collection = Profile.get_motor_collection()
    total = await collection.count_documents(filt)
    start = max(page - 1, 0) * page_size
    page_items = (
        await Profile.find(filt)
        .sort([(sort_field, direction)])
        .skip(start)
        .limit(page_size)
        .to_list()
    )

    # Clear soft/stale "failed" only for the current page
    for p in page_items:
        try:
            await heal_soft_scrape_failure(p)
        except Exception:
            pass

    pids = [str(p.id) for p in page_items]
    live_counts = await _live_programme_post_counts(pids)
    baselines = await _earliest_baselines(pids)
    items: list[ProfileResponse] = []
    for p in page_items:
        resp = to_profile_response(p)
        # Always prefer live programme-window count (0 is meaningful).
        resp.programme_posts = int(live_counts.get(str(p.id), 0))
        base = baselines.get(str(p.id))
        if base:
            _apply_follower_baseline(resp, baseline_followers=base[1], baseline_date=base[0])
        items.append(resp)

    return ProfileListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


async def get_profile(user_id: str, profile_id: str) -> Profile:
    profile = await Profile.get(profile_id)
    if not profile or profile.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    try:
        await heal_soft_scrape_failure(profile)
    except Exception:
        pass
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
