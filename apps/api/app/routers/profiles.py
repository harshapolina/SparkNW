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
from instascope_shared.services.profiles import to_profile_response
from fastapi import HTTPException

from app.scrape_queue import enqueue_profile_ids, mark_profiles_queued

router = APIRouter(prefix="/profiles", tags=["profiles"])

# Keep strong refs so one-off background tasks are not GC'd mid-flight (Python 3.12+).
_background_tasks: set[asyncio.Task] = set()


def _spawn_background(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


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
    """Create profile and queue scrape in the background (fast HTTP response).

    Awaiting the full scrape here left the browser Network tab on Pending for
    10+ minutes and often aborted the work. The durable scrape queue runs the
    same inline scraper after we return.
    """
    from datetime import datetime

    profile = await profile_service.add_profile(str(user.id), payload)
    profile.scrape_progress = {
        "active": True,
        "phase": "queued",
        "scraped_posts": 0,
        "total_posts": int(profile.posts_count or 0),
        "posts_left": int(profile.posts_count or 0),
        "percent": 0,
    }
    profile.updated_at = datetime.utcnow()
    await profile.save()
    await enqueue_profile_ids([str(profile.id)])
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


# ---------------------------------------------------------------------------
# Bulk routes MUST be registered before /{profile_id}/... or FastAPI treats
# "bulk" as a profile_id (e.g. POST /profiles/bulk/refresh → refresh("bulk")).
# ---------------------------------------------------------------------------


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
                duplicates += 1
                status_label = "duplicate"
                if row.student:
                    updated += 1
                    msg = "Already tracked — student fields merged"
                else:
                    msg = "Already tracked"
                # scrape_now means the operator asked to scrape — always queue,
                # including re-imports (previously skipped when last_success_at was set).
                if payload.scrape_now:
                    to_scrape.append(profile)
                    msg = f"{msg}; queued for scrape"
                elif getattr(profile, "last_success_at", None):
                    msg = f"{msg}; scrape skipped (already scraped)"
                else:
                    msg = f"{msg}; not scraped yet (scrape_now=false)"

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
        # Sequential queue — one scrape at a time (same path as single Add).
        ids = [str(p.id) for p in to_scrape]
        await mark_profiles_queued(ids)
        queued = await enqueue_profile_ids(ids)
        scraping = queued > 0

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
    """Queue refreshes sequentially in the API scrape queue (not on the request).

    Awaiting N sequential scrapes caused browser "Failed to fetch" timeouts.
    Fire-and-forget create_task loops often never ran — use the durable queue.
    """
    from datetime import datetime

    from instascope_shared.models import Job, JobStatus, JobType

    out: list[JobResponse] = []
    to_scrape: list[str] = []

    for pid in payload.ids:
        try:
            profile = await profile_service.get_profile(str(user.id), pid)
            job = Job(
                user_id=str(user.id),
                profile_id=str(profile.id),
                job_type=JobType.SCRAPE_PROFILE,
                status=JobStatus.PENDING,
                priority=1,
            )
            await job.insert()
            to_scrape.append(str(profile.id))
            out.append(
                JobResponse(
                    id=str(job.id),
                    profile_id=str(profile.id),
                    job_type=job.job_type.value if hasattr(job.job_type, "value") else str(job.job_type),
                    status=JobStatus.PENDING.value,
                    attempts=0,
                    error_message=None,
                    created_at=getattr(job, "created_at", None) or datetime.utcnow(),
                    finished_at=None,
                )
            )
        except Exception:
            import logging
            import traceback

            logging.getLogger("instascope.api.profiles").error(
                "bulk_refresh enqueue failed profile_id=%s\n%s",
                pid,
                traceback.format_exc(),
            )
            continue

    if to_scrape:
        await mark_profiles_queued(to_scrape)
        await enqueue_profile_ids(to_scrape)
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


# ---------------------------------------------------------------------------
# Single-profile routes (parameterized — must come after /bulk/*)
# ---------------------------------------------------------------------------


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
    """Queue a scrape and return immediately — do not await Instagram on the request.

    Website Refresh used to await the full scrape; the browser stayed Pending and
    often cancelled the server work. Queue uses the same scraper as terminal/API.
    """
    from datetime import datetime

    from instascope_shared.models import Job, JobStatus, JobType

    try:
        profile = await profile_service.get_profile(str(user.id), profile_id)
        profile.scrape_progress = {
            "active": True,
            "phase": "queued",
            "scraped_posts": 0,
            "total_posts": int(profile.posts_count or 0),
            "posts_left": int(profile.posts_count or 0),
            "percent": 0,
        }
        profile.updated_at = datetime.utcnow()
        await profile.save()
        job = Job(
            user_id=str(user.id),
            profile_id=str(profile.id),
            job_type=JobType.SCRAPE_PROFILE,
            status=JobStatus.PENDING,
            priority=1,
        )
        await job.insert()
        await enqueue_profile_ids([str(profile.id)], force=True)
        return [
            JobResponse(
                id=str(job.id),
                profile_id=str(profile.id),
                job_type=job.job_type.value if hasattr(job.job_type, "value") else str(job.job_type),
                status=JobStatus.PENDING.value,
                attempts=0,
                error_message=None,
                created_at=getattr(job, "created_at", None) or datetime.utcnow(),
                finished_at=None,
            )
        ]
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Refresh failed: {str(exc)[:240]}") from exc


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
