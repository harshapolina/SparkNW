from datetime import datetime

from fastapi import APIRouter, Depends

from app.deps import get_current_user, require_admin
from instascope_shared.models import User, UserSettings
from instascope_shared.schemas import (
    DailyScrapeSettingsResponse,
    DailyScrapeSettingsUpdateRequest,
    DailyYouTubeSyncSettingsResponse,
    DailyYouTubeSyncSettingsUpdateRequest,
    SettingsResponse,
    SettingsUpdateRequest,
)
from instascope_shared.services.app_config import (
    is_daily_scrape_enabled,
    is_daily_youtube_sync_enabled,
    set_daily_scrape_enabled,
    set_daily_youtube_sync_enabled,
)

router = APIRouter(prefix="/settings", tags=["settings"])


async def _get_or_create(user_id: str) -> UserSettings:
    settings = await UserSettings.find_one(UserSettings.user_id == user_id)
    if not settings:
        settings = UserSettings(user_id=user_id)
        await settings.insert()
    return settings


@router.get("", response_model=SettingsResponse)
async def get_settings(user: User = Depends(get_current_user)):
    s = await _get_or_create(str(user.id))
    return SettingsResponse(
        dark_mode=s.dark_mode,
        follower_growth_notify_pct=s.follower_growth_notify_pct,
        notify_followers_down=s.notify_followers_down,
        notify_scrape_failed=s.notify_scrape_failed,
        notify_engagement_spike=s.notify_engagement_spike,
        engagement_spike_pct=s.engagement_spike_pct,
        timezone=s.timezone,
    )


@router.patch("", response_model=SettingsResponse)
async def update_settings(payload: SettingsUpdateRequest, user: User = Depends(get_current_user)):
    s = await _get_or_create(str(user.id))
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(s, k, v)
    s.updated_at = datetime.utcnow()
    await s.save()
    return SettingsResponse(
        dark_mode=s.dark_mode,
        follower_growth_notify_pct=s.follower_growth_notify_pct,
        notify_followers_down=s.notify_followers_down,
        notify_scrape_failed=s.notify_scrape_failed,
        notify_engagement_spike=s.notify_engagement_spike,
        engagement_spike_pct=s.engagement_spike_pct,
        timezone=s.timezone,
    )


@router.get("/daily-scrape", response_model=DailyScrapeSettingsResponse)
async def get_daily_scrape_settings(_: User = Depends(require_admin)):
    """Admin: whether the scheduled morning scrape is allowed to run."""
    return DailyScrapeSettingsResponse(enabled=await is_daily_scrape_enabled())


@router.patch("/daily-scrape", response_model=DailyScrapeSettingsResponse)
async def update_daily_scrape_settings(
    payload: DailyScrapeSettingsUpdateRequest,
    _: User = Depends(require_admin),
):
    """Admin: turn auto Instagram scraping on/off. Stays until changed again.

    OFF — pause morning fan-out and drain/skip bulk auto queue (no env flip).
    ON — resume bulk unfinished profiles immediately; mornings run as scheduled.
    Manual Refresh stays available either way.
    """
    enabled = await set_daily_scrape_enabled(payload.enabled)
    if not enabled:
        from app.scrape_bulk import pause_bulk_auto_scraping

        await pause_bulk_auto_scraping()
    else:
        from app.scrape_bulk import ensure_bulk_worker, requeue_unfinished_bulk_profiles

        ensure_bulk_worker()
        await requeue_unfinished_bulk_profiles()
    return DailyScrapeSettingsResponse(enabled=enabled)


@router.get("/daily-youtube-sync", response_model=DailyYouTubeSyncSettingsResponse)
async def get_daily_youtube_sync_settings(_: User = Depends(require_admin)):
    """Admin: YouTube morning sync toggle (independent of Instagram daily scrape)."""
    return DailyYouTubeSyncSettingsResponse(enabled=await is_daily_youtube_sync_enabled())


@router.patch("/daily-youtube-sync", response_model=DailyYouTubeSyncSettingsResponse)
async def update_daily_youtube_sync_settings(
    payload: DailyYouTubeSyncSettingsUpdateRequest,
    _: User = Depends(require_admin),
):
    """Admin: turn daily YouTube sync on/off.

    ON — immediately enqueue sync jobs for all connected channels (shows on Scraping
    queue) and keep the morning Beat schedule enabled.
    """
    enabled = await set_daily_youtube_sync_enabled(payload.enabled)
    if enabled:
        from app.worker_client import dispatch_fanout_youtube, dispatch_youtube_sync_job
        from instascope_shared.services.youtube_jobs import enqueue_connected_youtube_syncs

        # Prefer creating jobs in-API then dispatching each task (visible immediately).
        try:
            summary = await enqueue_connected_youtube_syncs()
            dispatched = 0
            for job in summary.get("jobs") or []:
                tid = dispatch_youtube_sync_job(
                    job["job_id"],
                    job["profile_id"],
                    countdown=int(job.get("countdown") or 0),
                )
                if tid:
                    dispatched += 1
            if dispatched == 0 and summary.get("enqueued", 0) > 0:
                # Broker failed mid-way — still try Celery fanout as fallback
                dispatch_fanout_youtube()
        except Exception:
            dispatch_fanout_youtube()
    return DailyYouTubeSyncSettingsResponse(enabled=enabled)
