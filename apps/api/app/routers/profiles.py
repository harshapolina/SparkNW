import asyncio
import csv
import io
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse

from app.deps import get_current_user
from instascope_shared.models import Post, Profile, ProfileSnapshot, ProfileStatus, User
from instascope_shared.schemas import (
    AddProfileRequest,
    BulkIdsRequest,
    BulkImportRequest,
    BulkImportResponse,
    BulkImportItemResult,
    JobResponse,
    MessageResponse,
    PostResponse,
    ProfileListResponse,
    ProfileResponse,
    SnapshotResponse,
)
from instascope_shared.services import profiles as profile_service
from instascope_shared.services.inline_scrape import scrape_profile_inline
from instascope_shared.services.profiles import to_profile_response
from fastapi import HTTPException

router = APIRouter(prefix="/profiles", tags=["profiles"])


def _dispatch_jobs(jobs: list) -> bool:
    """Returns True if at least one job was handed to Celery."""
    dispatched = False
    try:
        from worker_client import dispatch_scrape_job

        for job in jobs:
            if job.profile_id:
                task_id = dispatch_scrape_job(str(job.id), str(job.profile_id))
                if task_id:
                    job.celery_task_id = task_id
                    dispatched = True
    except Exception:
        return False
    return dispatched


@router.post("", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED)
async def add_profile(payload: AddProfileRequest, user: User = Depends(get_current_user)):
    profile = await profile_service.add_profile(str(user.id), payload)
    # Immediate workable data: scrape inline (demo mode). Celery still handles daily batch.
    await scrape_profile_inline(profile)
    profile = await profile_service.get_profile(str(user.id), str(profile.id))
    return to_profile_response(profile)


@router.get("", response_model=ProfileListResponse)
async def list_profiles(
    user: User = Depends(get_current_user),
    q: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    sort_by: str = "updated_at",
    sort_dir: str = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    return await profile_service.list_profiles(
        str(user.id),
        q=q,
        status_filter=status_filter,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        page_size=page_size,
    )


@router.get("/{profile_id}", response_model=ProfileResponse)
async def get_profile(profile_id: str, user: User = Depends(get_current_user)):
    profile = await profile_service.get_profile(str(user.id), profile_id)
    return to_profile_response(profile)


@router.delete("/{profile_id}", response_model=MessageResponse)
async def delete_profile(profile_id: str, user: User = Depends(get_current_user)):
    await profile_service.delete_profiles(str(user.id), [profile_id])
    return MessageResponse(message="Profile deleted")


@router.post("/{profile_id}/refresh", response_model=list[JobResponse])
async def refresh_profile(profile_id: str, user: User = Depends(get_current_user)):
    """Enqueue scrape on the Celery worker — never block/crash the API with Playwright."""
    from datetime import datetime

    from instascope_shared.models import JobStatus

    profile = await profile_service.get_profile(str(user.id), profile_id)
    jobs = await profile_service.enqueue_refresh(str(user.id), [str(profile.id)], priority=1)
    if not jobs:
        raise HTTPException(status_code=500, detail="Could not create scrape job")

    job = jobs[0]
    dispatched = _dispatch_jobs([job])
    if dispatched and getattr(job, "celery_task_id", None):
        try:
            await job.save()
        except Exception:
            pass

    if not dispatched:
        # Celery/redis down — fall back to background task (still non-blocking for CORS/UI)
        async def _bg(pid: str) -> None:
            try:
                fresh = await Profile.get(pid)
                if fresh:
                    await scrape_profile_inline(fresh)
            except Exception:
                return

        asyncio.create_task(_bg(str(profile.id)))

    return [
        JobResponse(
            id=str(job.id),
            profile_id=str(profile.id),
            job_type=job.job_type.value if hasattr(job.job_type, "value") else str(job.job_type),
            status=JobStatus.PENDING.value,
            attempts=int(getattr(job, "attempts", 0) or 0),
            error_message=None,
            created_at=getattr(job, "created_at", None) or datetime.utcnow(),
            finished_at=None,
        )
    ]


@router.post("/{profile_id}/pause", response_model=ProfileResponse)
async def pause_profile(profile_id: str, user: User = Depends(get_current_user)):
    await profile_service.set_profiles_status(str(user.id), [profile_id], ProfileStatus.PAUSED)
    profile = await profile_service.get_profile(str(user.id), profile_id)
    return to_profile_response(profile)


@router.post("/{profile_id}/resume", response_model=ProfileResponse)
async def resume_profile(profile_id: str, user: User = Depends(get_current_user)):
    await profile_service.set_profiles_status(str(user.id), [profile_id], ProfileStatus.ACTIVE)
    profile = await profile_service.get_profile(str(user.id), profile_id)
    return to_profile_response(profile)


@router.get("/{profile_id}/posts", response_model=list[PostResponse])
async def list_posts(profile_id: str, user: User = Depends(get_current_user)):
    await profile_service.get_profile(str(user.id), profile_id)
    posts = await Post.find(Post.profile_id == profile_id).sort(-Post.posted_at).to_list()
    return [
        PostResponse(
            id=str(p.id),
            profile_id=p.profile_id,
            ig_post_id=p.ig_post_id,
            shortcode=p.shortcode,
            media_type=p.media_type.value if hasattr(p.media_type, "value") else str(p.media_type),
            caption=p.caption,
            thumbnail_url=p.thumbnail_url,
            permalink=p.permalink,
            likes=p.likes,
            comments=p.comments,
            views=p.views,
            posted_at=p.posted_at,
        )
        for p in posts
    ]


@router.get("/{profile_id}/history", response_model=list[SnapshotResponse])
async def list_history(profile_id: str, user: User = Depends(get_current_user)):
    await profile_service.get_profile(str(user.id), profile_id)
    snaps = (
        await ProfileSnapshot.find(ProfileSnapshot.profile_id == profile_id)
        .sort(-ProfileSnapshot.snapshot_date)
        .to_list()
    )
    return [
        SnapshotResponse(
            id=str(s.id),
            profile_id=s.profile_id,
            snapshot_date=s.snapshot_date,
            followers=s.followers,
            following=s.following,
            posts_count=s.posts_count,
            avg_likes=s.avg_likes,
            avg_views=s.avg_views,
            avg_comments=s.avg_comments,
            engagement_rate=s.engagement_rate,
            followers_growth=s.followers_growth,
            followers_growth_pct=s.followers_growth_pct,
        )
        for s in snaps
    ]


@router.post("/bulk/import", response_model=BulkImportResponse)
async def bulk_import(payload: BulkImportRequest, user: User = Depends(get_current_user)):
    """Import many profile URLs/usernames from a sheet. Optionally scrape in background."""
    from instascope_shared.schemas import BulkImportRow

    imported = 0
    skipped = 0
    failed = 0
    updated = 0
    duplicates = 0
    items: list[BulkImportItemResult] = []
    to_scrape: list = []

    # Prefer rich rows (with student roster fields); fall back to bare URLs
    work: list[BulkImportRow] = list(payload.rows or [])
    if not work:
        work = [BulkImportRow(url=u) for u in (payload.urls or [])]

    seen: set[str] = set()
    for row in work:
        raw = (row.url or "").strip()
        if not raw:
            failed += 1
            items.append(BulkImportItemResult(url="", status="failed", message="Missing Instagram URL"))
            continue
        key = raw.lower()
        if key in seen:
            skipped += 1
            items.append(BulkImportItemResult(url=raw, status="skipped", message="Duplicate in batch"))
            continue
        seen.add(key)

        try:
            req = AddProfileRequest(url=raw, student=dict(row.student or {}))
            try:
                profile = await profile_service.add_profile(str(user.id), req, upsert_student=False)
                imported += 1
                status_label = "imported"
                msg = None
                to_scrape.append(profile)
            except HTTPException as exc:
                if exc.status_code != 409:
                    raise
                profile = await profile_service.add_profile(str(user.id), req, upsert_student=True)
                already_scraped = bool(getattr(profile, "last_success_at", None))
                duplicates += 1
                status_label = "duplicate"
                if row.student:
                    updated += 1
                    msg = "Already tracked — student fields merged"
                else:
                    msg = "Already tracked"
                if already_scraped:
                    msg = f"{msg}; scrape skipped (already scraped)"
                else:
                    to_scrape.append(profile)

            items.append(
                BulkImportItemResult(
                    url=raw,
                    username=profile.username,
                    status=status_label,
                    profile_id=str(profile.id),
                    message=msg,
                )
            )
        except HTTPException as exc:
            failed += 1
            items.append(
                BulkImportItemResult(
                    url=raw,
                    status="failed",
                    message=str(exc.detail),
                )
            )
        except Exception as exc:  # noqa: BLE001
            failed += 1
            items.append(BulkImportItemResult(url=raw, status="failed", message=str(exc)))

    scraping = False
    if payload.scrape_now and to_scrape:
        scraping = True

        async def _scrape_all(profiles: list) -> None:
            for profile in profiles:
                try:
                    fresh = await Profile.get(str(profile.id))
                    if fresh:
                        await scrape_profile_inline(fresh)
                except Exception:
                    continue

        asyncio.create_task(_scrape_all(to_scrape))

    return BulkImportResponse(
        imported=imported,
        skipped=skipped,
        failed=failed,
        updated=updated,
        duplicates=duplicates,
        scraping=scraping,
        items=items,
    )


@router.post("/bulk/delete", response_model=MessageResponse)
async def bulk_delete(payload: BulkIdsRequest, user: User = Depends(get_current_user)):
    n = await profile_service.delete_profiles(str(user.id), payload.ids)
    return MessageResponse(message=f"Deleted {n} profiles")


@router.post("/bulk/refresh", response_model=list[JobResponse])
async def bulk_refresh(payload: BulkIdsRequest, user: User = Depends(get_current_user)):
    jobs = []
    for pid in payload.ids:
        try:
            profile = await profile_service.get_profile(str(user.id), pid)
            job = await scrape_profile_inline(profile)
            jobs.append(job)
        except Exception:
            continue
    out: list[JobResponse] = []
    for j in jobs:
        try:
            out.append(
                JobResponse(
                    id=str(j.id),
                    profile_id=str(j.profile_id),
                    job_type=j.job_type.value if hasattr(j.job_type, "value") else str(j.job_type),
                    status=j.status.value if hasattr(j.status, "value") else str(j.status),
                    attempts=j.attempts,
                    error_message=j.error_message,
                    created_at=j.created_at,
                    finished_at=j.finished_at,
                )
            )
        except Exception:
            continue
    return out


@router.post("/bulk/pause", response_model=MessageResponse)
async def bulk_pause(payload: BulkIdsRequest, user: User = Depends(get_current_user)):
    n = await profile_service.set_profiles_status(str(user.id), payload.ids, ProfileStatus.PAUSED)
    return MessageResponse(message=f"Paused {n} profiles")


@router.post("/bulk/resume", response_model=MessageResponse)
async def bulk_resume(payload: BulkIdsRequest, user: User = Depends(get_current_user)):
    n = await profile_service.set_profiles_status(str(user.id), payload.ids, ProfileStatus.ACTIVE)
    return MessageResponse(message=f"Resumed {n} profiles")


@router.post("/bulk/export")
async def bulk_export(payload: BulkIdsRequest, user: User = Depends(get_current_user)):
    profiles = []
    for pid in payload.ids:
        p = await Profile.get(pid)
        if p and p.user_id == str(user.id):
            profiles.append(p)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "username",
            "followers",
            "following",
            "posts",
            "avg_likes",
            "avg_views",
            "growth_pct",
            "status",
            "url",
        ]
    )
    for p in profiles:
        writer.writerow(
            [
                p.username,
                p.followers,
                p.following,
                p.posts_count,
                p.avg_likes,
                p.avg_views,
                p.growth_pct_today,
                p.status.value if hasattr(p.status, "value") else p.status,
                p.profile_url,
            ]
        )
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=instascope-profiles.csv"},
    )
