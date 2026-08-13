"""YouTube connect + sync pipeline (separate from Instagram scrape).

Flow:
1. connect_youtube_channel(profile, url_or_handle) — resolve once, store UC… id
2. sync_youtube_channel(profile_id | channel) — channels.list by id, uploads playlist,
   videos.list (batched), upsert videos, write daily YouTubeSnapshot

Does not touch scrape_core / Playwright / Decodo.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from instascope_shared.models import (
    Profile,
    YouTubeChannel,
    YouTubeSnapshot,
    YouTubeSyncStatus,
    YouTubeVideo,
)
from instascope_shared.services.youtube_client import YouTubeClient, YouTubeChannelInfo
from instascope_shared.services.youtube_errors import (
    YouTubeError,
    YouTubeNotFoundError,
    YouTubeQuotaExceededError,
    YouTubeUnavailableError,
)

logger = logging.getLogger("instascope.youtube.sync")

# First connect / deep sync: how many newest uploads to pull (quota-aware).
DEFAULT_MAX_VIDEOS = 50


def _parse_yt_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        # YouTube uses RFC3339 with Z
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def _channel_url(info: YouTubeChannelInfo) -> str:
    if info.custom_url:
        handle = info.custom_url if str(info.custom_url).startswith("@") else f"@{info.custom_url}"
        return f"https://www.youtube.com/{handle.lstrip('/')}"
    return f"https://www.youtube.com/channel/{info.channel_id}"


def _handle_from_info(info: YouTubeChannelInfo) -> str | None:
    if not info.custom_url:
        return None
    raw = str(info.custom_url).strip()
    return raw if raw.startswith("@") else f"@{raw}"


def _map_sync_error(exc: Exception) -> tuple[YouTubeSyncStatus, str]:
    msg = str(exc)[:500]
    if isinstance(exc, YouTubeQuotaExceededError):
        return YouTubeSyncStatus.QUOTA_EXCEEDED, msg
    if isinstance(exc, (YouTubeNotFoundError, YouTubeUnavailableError)):
        return YouTubeSyncStatus.UNAVAILABLE, msg
    if isinstance(exc, YouTubeError):
        return YouTubeSyncStatus.FAILED, msg
    return YouTubeSyncStatus.FAILED, msg


async def connect_youtube_channel(
    profile: Profile,
    url_or_handle: str,
    *,
    client: YouTubeClient | None = None,
    max_videos: int = DEFAULT_MAX_VIDEOS,
    sync_videos: bool = True,
) -> dict[str, Any]:
    """Resolve channel once, persist YouTubeChannel + Profile refs, optional first sync."""
    owns = client is None
    yt = client or YouTubeClient()
    try:
        info = await yt.resolve_channel(url_or_handle, allow_search=True)
        doc = await _upsert_channel_from_info(profile, info, source_url=url_or_handle.strip())
        profile.youtube_channel_id = info.channel_id
        profile.youtube_connected = True
        profile.updated_at = datetime.utcnow()
        await profile.save()

        result: dict[str, Any] = {
            "connected": True,
            "channel_id": info.channel_id,
            "channel_name": info.title,
            "handle": _handle_from_info(info),
            "youtube_channel_id": str(doc.id),
        }
        if sync_videos:
            sync_result = await sync_youtube_channel(
                str(profile.id),
                client=yt,
                max_videos=max_videos,
            )
            result["sync"] = sync_result
        return result
    finally:
        if owns:
            await yt.aclose()


async def _upsert_channel_from_info(
    profile: Profile,
    info: YouTubeChannelInfo,
    *,
    source_url: str | None = None,
) -> YouTubeChannel:
    now = datetime.utcnow()
    existing = await YouTubeChannel.find_one(YouTubeChannel.profile_id == str(profile.id))
    if not existing:
        # Channel ID might already be linked to another profile — surface clearly
        by_cid = await YouTubeChannel.find_one(YouTubeChannel.channel_id == info.channel_id)
        if by_cid and by_cid.profile_id != str(profile.id):
            raise YouTubeUnavailableError(
                f"YouTube channel {info.channel_id} is already linked to another profile"
            )
        existing = YouTubeChannel(
            profile_id=str(profile.id),
            user_id=profile.user_id,
            org_id=getattr(profile, "org_id", None) or "spark",
            channel_id=info.channel_id,
        )

    existing.channel_id = info.channel_id
    existing.channel_url = source_url or _channel_url(info)
    existing.handle = _handle_from_info(info)
    existing.channel_name = info.title
    existing.description = info.description
    existing.thumbnail_url = info.thumbnail_url
    existing.subscriber_count = info.subscriber_count
    existing.hidden_subscriber_count = info.hidden_subscriber_count
    existing.view_count = info.view_count
    existing.video_count = info.video_count
    existing.uploads_playlist_id = info.uploads_playlist_id
    existing.connected = True
    existing.updated_at = now
    if existing.id is None:
        await existing.insert()
    else:
        await existing.save()
    return existing


async def sync_youtube_channel(
    profile_id: str,
    *,
    client: YouTubeClient | None = None,
    max_videos: int = DEFAULT_MAX_VIDEOS,
    fetch_videos: bool = True,
) -> dict[str, Any]:
    """Refresh public channel metrics + videos + daily snapshot for one profile.

    Uses stored channel_id only (no search.list). Failures are recorded on the
    YouTubeChannel document; callers for bulk fan-out should catch and continue.
    """
    profile = await Profile.get(profile_id)
    if not profile:
        raise YouTubeNotFoundError(f"Profile not found: {profile_id}")

    channel = await YouTubeChannel.find_one(YouTubeChannel.profile_id == profile_id)
    channel_id = (channel.channel_id if channel else None) or profile.youtube_channel_id
    if not channel_id:
        raise YouTubeUnavailableError("Profile has no connected YouTube channel_id")

    owns = client is None
    yt = client or YouTubeClient()
    try:
        info = await yt.get_channel_by_id(channel_id)
        channel = await _upsert_channel_from_info(profile, info, source_url=channel.channel_url if channel else None)

        videos_upserted = 0
        if fetch_videos and channel.uploads_playlist_id:
            videos_upserted = await _sync_videos(
                yt,
                profile=profile,
                channel=channel,
                max_videos=max_videos,
            )

        likes_sum, comments_sum = await _sum_video_engagement(channel.channel_id)
        snap = await _upsert_snapshot(
            profile=profile,
            channel=channel,
            likes=likes_sum,
            comments=comments_sum,
        )

        now = datetime.utcnow()
        channel.sync_status = YouTubeSyncStatus.SUCCESS
        channel.last_error = None
        channel.last_synced_at = now
        channel.updated_at = now
        await channel.save()

        profile.youtube_channel_id = channel.channel_id
        profile.youtube_connected = True
        profile.youtube_last_synced_at = now
        profile.updated_at = now
        await profile.save()

        return {
            "ok": True,
            "profile_id": profile_id,
            "channel_id": channel.channel_id,
            "subscribers": channel.subscriber_count,
            "total_views": channel.view_count,
            "video_count": channel.video_count,
            "videos_upserted": videos_upserted,
            "snapshot_date": snap.snapshot_date,
            "sync_status": channel.sync_status.value,
        }
    except Exception as exc:
        status, msg = _map_sync_error(exc)
        logger.warning(
            "YouTube sync failed profile_id=%s channel_id=%s status=%s err=%s",
            profile_id,
            channel_id,
            status.value,
            msg,
        )
        if channel is None:
            channel = await YouTubeChannel.find_one(YouTubeChannel.profile_id == profile_id)
        if channel is not None:
            channel.sync_status = status
            channel.last_error = msg
            channel.updated_at = datetime.utcnow()
            await channel.save()
        raise
    finally:
        if owns:
            await yt.aclose()


async def _sync_videos(
    yt: YouTubeClient,
    *,
    profile: Profile,
    channel: YouTubeChannel,
    max_videos: int,
) -> int:
    video_ids: list[str] = []
    async for vid in yt.iter_upload_video_ids(
        channel.uploads_playlist_id or "",
        max_videos=max_videos,
    ):
        video_ids.append(vid)
    if not video_ids:
        return 0

    infos = await yt.list_videos(video_ids)
    now = datetime.utcnow()
    upserted = 0
    for info in infos:
        existing = await YouTubeVideo.find_one(YouTubeVideo.video_id == info.video_id)
        url = f"https://www.youtube.com/watch?v={info.video_id}"
        if not existing:
            existing = YouTubeVideo(
                profile_id=str(profile.id),
                user_id=profile.user_id,
                channel_id=channel.channel_id,
                video_id=info.video_id,
            )
        existing.title = info.title
        existing.url = url
        existing.published_at = _parse_yt_datetime(info.published_at)
        existing.thumbnail_url = info.thumbnail_url
        existing.view_count = info.view_count
        existing.like_count = info.like_count
        existing.comment_count = info.comment_count
        existing.duration = info.duration
        existing.updated_at = now
        if existing.id is None:
            await existing.insert()
        else:
            await existing.save()
        upserted += 1
    return upserted


async def _sum_video_engagement(channel_id: str) -> tuple[int, int]:
    likes = 0
    comments = 0
    async for row in YouTubeVideo.find(YouTubeVideo.channel_id == channel_id):
        if row.like_count is not None:
            likes += int(row.like_count)
        if row.comment_count is not None:
            comments += int(row.comment_count)
    return likes, comments


async def _upsert_snapshot(
    *,
    profile: Profile,
    channel: YouTubeChannel,
    likes: int,
    comments: int,
) -> YouTubeSnapshot:
    day = datetime.utcnow().strftime("%Y-%m-%d")
    snap = await YouTubeSnapshot.find_one(
        YouTubeSnapshot.profile_id == str(profile.id),
        YouTubeSnapshot.snapshot_date == day,
    )
    if not snap:
        snap = YouTubeSnapshot(
            profile_id=str(profile.id),
            user_id=profile.user_id,
            channel_id=channel.channel_id,
            snapshot_date=day,
        )
    snap.channel_id = channel.channel_id
    snap.subscribers = channel.subscriber_count
    snap.total_views = channel.view_count
    snap.video_count = channel.video_count
    snap.likes = likes
    snap.comments = comments
    if snap.id is None:
        await snap.insert()
    else:
        await snap.save()
    return snap


async def mark_youtube_disconnected(profile: Profile) -> None:
    """Clear Profile YouTube refs; keep historical channel/videos/snapshots."""
    channel = await YouTubeChannel.find_one(YouTubeChannel.profile_id == str(profile.id))
    if channel:
        channel.connected = False
        channel.updated_at = datetime.utcnow()
        await channel.save()
    profile.youtube_connected = False
    profile.youtube_channel_id = None
    profile.youtube_last_synced_at = None
    profile.updated_at = datetime.utcnow()
    await profile.save()
