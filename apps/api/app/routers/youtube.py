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
from instascope_shared.services.youtube_sync import connect_youtube_channel, sync_youtube_channel

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


@router.get("/profiles/{profile_id}", response_model=YouTubeChannelResponse)
async def get_profile_youtube(profile_id: str, _: User = Depends(require_admin)):
    doc = await YouTubeChannel.find_one(YouTubeChannel.profile_id == profile_id)
    if not doc:
        raise HTTPException(status_code=404, detail="No YouTube channel linked to this profile")
    return _channel_response(doc)


@router.post("/profiles/{profile_id}/connect", response_model=YouTubeChannelResponse)
async def connect_profile_youtube(
    profile_id: str,
    payload: YouTubeConnectRequest,
    _: User = Depends(require_admin),
):
    """Resolve + store channel ID permanently, then sync public data for ONE profile."""
    profile = await Profile.get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    try:
        await connect_youtube_channel(
            profile,
            payload.url,
            max_videos=payload.max_videos,
            sync_videos=payload.sync_videos,
        )
    except Exception as exc:  # noqa: BLE001
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
    body = payload or YouTubeSyncRequest()
    try:
        return await sync_youtube_channel(
            profile_id,
            max_videos=body.max_videos,
            fetch_videos=body.fetch_videos,
        )
    except Exception as exc:  # noqa: BLE001
        raise _http_for_youtube(exc) from exc
