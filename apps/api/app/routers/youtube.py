"""YouTube Data API endpoints — connect / sync one channel (admin).

Server-side YOUTUBE_API_KEY only. Does not touch Instagram scrape paths.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import require_admin
from instascope_shared.models import Profile, User, YouTubeChannel
from instascope_shared.schemas import (
    YouTubeChannelResponse,
    YouTubeConnectRequest,
    YouTubeInsightsResponse,
    YouTubeResolveResponse,
    YouTubeSyncRequest,
)
from instascope_shared.services.youtube_client import YouTubeClient
from instascope_shared.services.youtube_errors import (
    YouTubeConfigError,
    YouTubeError,
    YouTubeInvalidChannelError,
    YouTubeNotFoundError,
    YouTubeQuotaExceededError,
)
from instascope_shared.services.youtube_sync import (
    connect_youtube_channel,
    get_youtube_insights,
    sync_youtube_channel,
)
from instascope_shared.services.youtube_jobs import get_youtube_sync_status

router = APIRouter(prefix="/youtube", tags=["youtube"])


def _http_for_youtube(exc: Exception) -> HTTPException:
    if isinstance(exc, YouTubeConfigError):
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    if isinstance(exc, YouTubeQuotaExceededError):
        return HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc))
    if isinstance(exc, (YouTubeInvalidChannelError, YouTubeNotFoundError)):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, YouTubeError):
        return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)[:400])


def _channel_response(doc: YouTubeChannel) -> YouTubeChannelResponse:
    return YouTubeChannelResponse(
        profile_id=doc.profile_id,
        channel_id=doc.channel_id,
        channel_url=doc.channel_url,
        handle=doc.handle,
        channel_name=doc.channel_name,
        thumbnail_url=doc.thumbnail_url,
        subscriber_count=doc.subscriber_count,
        hidden_subscriber_count=doc.hidden_subscriber_count,
        view_count=doc.view_count,
        video_count=doc.video_count,
        connected=doc.connected,
        sync_status=doc.sync_status.value if hasattr(doc.sync_status, "value") else str(doc.sync_status),
        last_error=doc.last_error,
        last_synced_at=doc.last_synced_at,
    )


@router.post("/resolve", response_model=YouTubeResolveResponse)
async def resolve_youtube_channel(
    payload: YouTubeConnectRequest,
    _: User = Depends(require_admin),
):
    """Admin test: resolve one URL/handle without writing to MongoDB."""
    try:
        async with YouTubeClient() as yt:
            info = await yt.resolve_channel(payload.url, allow_search=True)
        handle = None
        if info.custom_url:
            handle = info.custom_url if str(info.custom_url).startswith("@") else f"@{info.custom_url}"
        return YouTubeResolveResponse(
            channel_id=info.channel_id,
            title=info.title,
            handle=handle,
            subscribers=info.subscriber_count,
            views=info.view_count,
            videos=info.video_count,
            thumbnail=info.thumbnail_url,
        )
    except Exception as exc:  # noqa: BLE001
        raise _http_for_youtube(exc) from exc


@router.get("/sync-status")
async def youtube_sync_status(_: User = Depends(require_admin)):
    """Live YouTube sync queue + recent job history for the Scraping page."""
    return await get_youtube_sync_status()


@router.post("/sync-all")
async def youtube_sync_all(_: User = Depends(require_admin)):
    """Admin: resume leftover YouTube jobs; skip channels already synced successfully."""
    from app.worker_client import dispatch_fanout_youtube, dispatch_youtube_job_payloads
    from instascope_shared.services.youtube_jobs import resume_unfinished_youtube_syncs

    summary = await resume_unfinished_youtube_syncs(
        reset_stale_running=False,
        skip_successful=True,
    )
    jobs = list(summary.get("resumed_jobs") or []) + list(summary.get("jobs") or [])
    dispatched = dispatch_youtube_job_payloads(jobs)
    if dispatched == 0 and (int(summary.get("enqueued") or 0) + int(summary.get("resumed") or 0)) > 0:
        task_id = dispatch_fanout_youtube()
        return {
            **{k: v for k, v in summary.items() if k not in {"jobs", "resumed_jobs"}},
            "dispatched": 0,
            "fanout_task_id": task_id,
        }
    return {
        **{k: v for k, v in summary.items() if k not in {"jobs", "resumed_jobs"}},
        "dispatched": dispatched,
    }


@router.get("/profiles/{profile_id}", response_model=YouTubeChannelResponse)
async def get_profile_youtube(profile_id: str, _: User = Depends(require_admin)):
    doc = await YouTubeChannel.find_one(YouTubeChannel.profile_id == profile_id)
    if not doc:
        raise HTTPException(status_code=404, detail="No YouTube channel linked to this profile")
    return _channel_response(doc)


@router.get("/profiles/{profile_id}/insights", response_model=YouTubeInsightsResponse)
async def get_profile_youtube_insights(profile_id: str, _: User = Depends(require_admin)):
    """Channel + all public video fields for uploads on/after programme start (15 Jul)."""
    data = await get_youtube_insights(profile_id)
    return YouTubeInsightsResponse(**data)


@router.post("/profiles/{profile_id}/connect", response_model=YouTubeChannelResponse)
async def connect_profile_youtube(
    profile_id: str,
    payload: YouTubeConnectRequest,
    _: User = Depends(require_admin),
):
    """Resolve + store channel ID permanently, then sync public data for ONE profile."""
    from datetime import datetime

    from instascope_shared.models import Job, JobStatus, JobType

    profile = await Profile.get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    job = Job(
        user_id=profile.user_id,
        profile_id=profile_id,
        job_type=JobType.SYNC_YOUTUBE,
        status=JobStatus.RUNNING,
        priority=3,
        started_at=datetime.utcnow(),
        meta={"source": "connect", "url": payload.url[:200]},
    )
    await job.insert()
    try:
        await connect_youtube_channel(
            profile,
            payload.url,
            max_videos=payload.max_videos,
            sync_videos=payload.sync_videos,
        )
        job.status = JobStatus.SUCCESS
        job.finished_at = datetime.utcnow()
        job.error_message = None
        await job.save()
    except Exception as exc:  # noqa: BLE001
        job.status = JobStatus.FAILED
        job.error_message = str(exc)[:280]
        job.finished_at = datetime.utcnow()
        await job.save()
        raise _http_for_youtube(exc) from exc
    doc = await YouTubeChannel.find_one(YouTubeChannel.profile_id == profile_id)
    if not doc:
        raise HTTPException(status_code=500, detail="Connect succeeded but channel doc missing")
    return _channel_response(doc)


@router.post("/profiles/{profile_id}/sync")
async def sync_profile_youtube(
    profile_id: str,
    payload: YouTubeSyncRequest | None = None,
    _: User = Depends(require_admin),
):
    """Re-sync one already-connected channel (uses stored channel_id — no search.list)."""
    from datetime import datetime

    from instascope_shared.models import Job, JobStatus, JobType

    profile = await Profile.get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    body = payload or YouTubeSyncRequest()
    job = Job(
        user_id=profile.user_id,
        profile_id=profile_id,
        job_type=JobType.SYNC_YOUTUBE,
        status=JobStatus.RUNNING,
        priority=3,
        started_at=datetime.utcnow(),
        meta={"source": "manual_sync"},
    )
    await job.insert()
    try:
        result = await sync_youtube_channel(
            profile_id,
            max_videos=body.max_videos,
            fetch_videos=body.fetch_videos,
        )
        job.status = JobStatus.SUCCESS
        job.finished_at = datetime.utcnow()
        job.error_message = None
        job.meta = {**(job.meta or {}), "youtube": result}
        await job.save()
        return result
    except Exception as exc:  # noqa: BLE001
        job.status = JobStatus.FAILED
        job.error_message = str(exc)[:280]
        job.finished_at = datetime.utcnow()
        await job.save()
        raise _http_for_youtube(exc) from exc
