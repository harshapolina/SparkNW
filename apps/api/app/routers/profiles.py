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
    UpdateProfileRequest,
)
from instascope_shared.services import profiles as profile_service
from instascope_shared.services.profiles import list_posts_in_programme_window, to_profile_response, to_profile_response_cohort
from fastapi import HTTPException

from app.scrape_bulk import (
    enqueue_bulk_profile_ids,
    mark_profiles_queued,
    pending_count as bulk_pending_count,
    sample_pending_count,
    deep_pending_count,
    running_profile_id as bulk_running_id,
    running_mode as bulk_running_mode,
)
from app.scrape_single import schedule_single_scrape, single_scrape_running

router = APIRouter(prefix="/profiles", tags=["profiles"])

# Keep strong refs so one-off background tasks are not GC'd mid-flight (Python 3.12+).
_background_tasks: set[asyncio.Task] = set()


def _spawn_background(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


@router.post("", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED)
async def add_profile(payload: AddProfileRequest, user: User = Depends(get_current_user)):
    """Create profile and scrape via the SINGLE runner (not the bulk queue)."""
    from instascope_shared.models import Job, JobStatus, JobType

    profile = await profile_service.add_profile(str(user.id), payload)
    job = Job(
        user_id=str(user.id),
        profile_id=str(profile.id),
        job_type=JobType.SCRAPE_PROFILE,
        status=JobStatus.PENDING,
        priority=1,
    )
    await job.insert()
    await schedule_single_scrape(str(profile.id), force=True, job=job)
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


@router.get("/scrape-status")
async def scrape_status(user: User = Depends(get_current_user)):
    """Live scrape activity for progress UI (who is scraping, posts scraped/total)."""
    active = await Profile.find({"scrape_progress.active": True}).to_list()
    # Prefer this user's profiles when multi-tenant; still show org-wide if shared admin.
    mine = [p for p in active if str(p.user_id) == str(user.id)]
    rows = mine if mine else active

    def _item(p: Profile) -> dict:
        prog = dict(getattr(p, "scrape_progress", None) or {})
        scraped = int(prog.get("scraped_posts") or 0)
        total = int(prog.get("total_posts") or p.posts_count or 0)
        if total > 0:
            percent = min(100, int(round(100 * scraped / total)))
        else:
            percent = int(prog.get("percent") or 0)
        left = max(0, total - scraped) if total > 0 else int(prog.get("posts_left") or 0)
        return {
            "profile_id": str(p.id),
            "username": p.username,
            "full_name": p.full_name or (getattr(p, "student", None) or {}).get("full_name"),
            "source": prog.get("source"),
            "phase": prog.get("phase") or "queued",
            "scraped_posts": scraped,
            "total_posts": total,
            "posts_left": left,
            "percent": percent,
            "active": bool(prog.get("active")),
        }

    queue = [_item(p) for p in rows]
    # Sort: currently scraping (non-queued phases) first, then by updated progress.
    def _rank(it: dict) -> tuple:
        phase = str(it.get("phase") or "")
        runningish = 0 if phase not in {"queued", ""} else 1
        return (runningish, -int(it.get("percent") or 0))

    queue.sort(key=_rank)

    running = None
    bulk_run = bulk_running_id()
    if bulk_run:
        for it in queue:
            if it["profile_id"] == bulk_run:
                running = it
                break
    if running is None:
        for it in queue:
            if it["phase"] not in {"queued", ""} and it["active"]:
                running = it
                break
    if running is None and queue:
        # Fall back to first active / single-running
        for it in queue:
            if single_scrape_running(it["profile_id"]):
                running = it
                break
        if running is None:
            running = queue[0]

    return {
        "running": running,
        "queue": queue,
        "active_count": len(queue),
        "pending_bulk": sample_pending_count(),
        "pending_deep": deep_pending_count(),
        "pending_total": bulk_pending_count(),
        "running_mode": bulk_running_mode(),
        "single_running": sum(1 for it in queue if single_scrape_running(it["profile_id"])),
    }


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
        # BULK queue — await enqueue so the worker starts before the HTTP response.
        ids = [str(p.id) for p in to_scrape]
        await mark_profiles_queued(ids)
        queued = await enqueue_bulk_profile_ids(ids, force=True)
        scraping = queued > 0

    # Auto-connect + sync YouTube when roster rows include a link/@handle.
    from app.worker_client import dispatch_youtube_connect_job
    from instascope_shared.services.youtube_jobs import (
        enqueue_youtube_connects,
        youtube_ref_from_student,
    )

    yt_items: list[tuple[str, str, str]] = []
    for row, item in zip(work, items, strict=False):
        if item.status not in {"imported", "duplicate"} or not item.profile_id:
            continue
        ref = youtube_ref_from_student(dict(row.student or {}))
        if not ref:
            continue
        profile = await Profile.get(item.profile_id)
        if not profile:
            continue
        yt_items.append((item.profile_id, str(profile.user_id), ref))

    youtube_queued = 0
    if yt_items:
        yt_summary = await enqueue_youtube_connects(yt_items, source="bulk_import")
        for job in yt_summary.get("jobs") or []:
            if dispatch_youtube_connect_job(
                job["job_id"],
                job["profile_id"],
                job["url"],
                countdown=int(job.get("countdown") or 0),
            ):
                youtube_queued += 1
        by_pid = {j["profile_id"] for j in (yt_summary.get("jobs") or [])}
        for item in items:
            if item.profile_id and item.profile_id in by_pid:
                extra = "YouTube connect+sync queued"
                item.message = f"{item.message}; {extra}" if item.message else extra

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
    """Queue refreshes on the BULK sequential worker (not the single runner)."""
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
        await enqueue_bulk_profile_ids(to_scrape)
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
    return await to_profile_response_cohort(profile)


@router.patch("/{profile_id}", response_model=ProfileResponse)
async def update_profile(
    profile_id: str,
    payload: UpdateProfileRequest,
    user: User = Depends(get_current_user),
):
    """Change Instagram handle/URL. Existing Refresh then scrapes the new account."""
    profile = await profile_service.update_profile_instagram(str(user.id), profile_id, payload)
    return await to_profile_response_cohort(profile)


@router.delete("/{profile_id}", response_model=MessageResponse)
async def delete_profile(profile_id: str, user: User = Depends(get_current_user)):
    await profile_service.delete_profiles(str(user.id), [profile_id])
    return MessageResponse(message="Profile deleted")


@router.post("/{profile_id}/refresh", response_model=list[JobResponse])
async def refresh_profile(profile_id: str, user: User = Depends(get_current_user)):
    """Scrape ONE profile via the single runner — never waits behind bulk import."""
    from datetime import datetime

    from instascope_shared.models import Job, JobStatus, JobType

    try:
        profile = await profile_service.get_profile(str(user.id), profile_id)
        job = Job(
            user_id=str(user.id),
            profile_id=str(profile.id),
            job_type=JobType.SCRAPE_PROFILE,
            status=JobStatus.PENDING,
            priority=1,
        )
        await job.insert()
        await schedule_single_scrape(str(profile.id), force=True, job=job)
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
    posts = await list_posts_in_programme_window(profile_id)
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
    from instascope_shared.cohort import snapshot_floor_ymd

    since = snapshot_floor_ymd()
    snaps = (
        await ProfileSnapshot.find(
            ProfileSnapshot.profile_id == profile_id,
            ProfileSnapshot.snapshot_date >= since,
        )
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
