"""YouTube connect + sync pipeline (separate from Instagram scrape).

Flow:
1. connect_youtube_channel(profile, url_or_handle) — resolve once, store UC… id
2. sync_youtube_channel(profile_id | channel) — channels.list by id, uploads playlist,
   videos.list (batched), upsert videos published on/after programme start (15 Jul),
   write daily YouTubeSnapshot

Does not touch scrape_core / Playwright / Decodo.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from instascope_shared.cohort import cohort_start_date, cohort_start_dt, cohort_start_ymd
from instascope_shared.models import (
    Profile,
    YouTubeChannel,
    YouTubeSnapshot,
    YouTubeSyncStatus,
    YouTubeVideo,
)
from instascope_shared.services.youtube_client import YouTubeClient, YouTubeChannelInfo, YouTubeVideoInfo
from instascope_shared.services.youtube_errors import (
    YouTubeError,
    YouTubeNotFoundError,
    YouTubeQuotaExceededError,
    YouTubeUnavailableError,
)

logger = logging.getLogger("instascope.youtube.sync")

# 0 = all uploads on/after programme start (SPARK_COHORT_START / 15 Jul 2026).
DEFAULT_MAX_VIDEOS = 0
# Safety only when a positive max_videos is passed; 0/None = unlimited until date floor.
HARD_MAX_VIDEOS = 50_000
# YouTube Shorts max length is 3 minutes; Data API has no dedicated isShort flag.
SHORTS_MAX_SECONDS = 180

_ISO8601_DURATION_RE = re.compile(
    r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$",
    re.IGNORECASE,
)


def parse_iso8601_duration_seconds(value: str | None) -> int | None:
    """Parse YouTube contentDetails.duration (e.g. PT1M5S) → seconds."""
    if not value:
        return None
    m = _ISO8601_DURATION_RE.match(str(value).strip())
    if not m:
        return None
    days = int(m.group("days") or 0)
    hours = int(m.group("hours") or 0)
    minutes = int(m.group("minutes") or 0)
    seconds = int(m.group("seconds") or 0)
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def classify_youtube_short(
    *,
    duration: str | None,
    title: str | None = None,
    description: str | None = None,
    tags: list[str] | tuple[str, ...] | None = None,
) -> tuple[bool, int | None]:
    """Return (is_short, duration_seconds).

    Heuristic (Data API has no official Shorts flag):
    - #shorts / #short in title, description, or tags → Short
    - duration ≤ 180s (current Shorts max) → Short
    - else → long-form
    """
    secs = parse_iso8601_duration_seconds(duration)
    blob = " ".join(
        [
            str(title or ""),
            str(description or ""),
            " ".join(str(t) for t in (tags or ())),
        ]
    ).lower()
    if "#shorts" in blob or "#short" in blob or " #shorts" in blob:
        return True, secs
    if any(str(t).lower() in {"shorts", "short", "#shorts", "#short"} for t in (tags or ())):
        return True, secs
    if secs is not None and 0 < secs <= SHORTS_MAX_SECONDS:
        return True, secs
    return False, secs


def _parse_yt_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        # YouTube uses RFC3339 with Z
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def _effective_max_videos(max_videos: int | None) -> int | None:
    """0 / None → no cap (paginate until programme-start floor). Positive → capped."""
    if max_videos is None or int(max_videos) <= 0:
        return None
    return min(int(max_videos), HARD_MAX_VIDEOS)


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


def _apply_video_fields(existing: YouTubeVideo, info: YouTubeVideoInfo, *, profile: Profile, channel: YouTubeChannel) -> None:
    from instascope_shared.services.youtube_client import _thumbnails_map

    raw = dict(info.raw or {})
    snippet = raw.get("snippet") or {}
    content = raw.get("contentDetails") or {}
    topic = raw.get("topicDetails") or {}
    recording = raw.get("recordingDetails") or {}
    live = raw.get("liveStreamingDetails") or {}
    player = raw.get("player") or {}

    existing.profile_id = str(profile.id)
    existing.user_id = profile.user_id
    existing.channel_id = channel.channel_id
    existing.title = info.title
    existing.description = info.description or ""
    existing.url = f"https://www.youtube.com/watch?v={info.video_id}"
    existing.published_at = _parse_yt_datetime(info.published_at)
    existing.thumbnail_url = info.thumbnail_url
    existing.thumbnails = _thumbnails_map(snippet.get("thumbnails"))
    existing.channel_title = info.channel_title
    existing.tags = list(info.tags or ())
    existing.category_id = info.category_id
    existing.live_broadcast_content = info.live_broadcast_content
    existing.default_language = info.default_language
    existing.default_audio_language = info.default_audio_language
    existing.topic_categories = [str(x) for x in (topic.get("topicCategories") or []) if x]
    existing.recording_date = recording.get("recordingDate")
    existing.live_streaming = dict(live) if isinstance(live, dict) else {}
    existing.player_embed_html = player.get("embedHtml")
    existing.localizations = dict(raw.get("localizations") or {})
    existing.content_rating = dict(content.get("contentRating") or {})
    existing.region_restriction = dict(content.get("regionRestriction") or {})
    existing.public_api = raw
    existing.view_count = info.view_count
    existing.like_count = info.like_count
    existing.comment_count = info.comment_count
    existing.favorite_count = info.favorite_count
    existing.duration = info.duration
    is_short, duration_seconds = classify_youtube_short(
        duration=info.duration,
        title=info.title,
        description=info.description,
        tags=list(info.tags or ()),
    )
    existing.duration_seconds = duration_seconds
    existing.is_short = is_short
    existing.dimension = info.dimension
    existing.definition = info.definition
    existing.caption = info.caption
    existing.licensed_content = info.licensed_content
    existing.projection = info.projection
    existing.privacy_status = info.privacy_status
    existing.upload_status = info.upload_status
    existing.license = info.license
    existing.embeddable = info.embeddable
    existing.public_stats_viewable = info.public_stats_viewable
    existing.made_for_kids = info.made_for_kids
    existing.updated_at = datetime.utcnow()


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
    raw = dict(info.raw or {})
    snippet = raw.get("snippet") or {}
    branding = raw.get("brandingSettings") or {}
    image = branding.get("image") or {}
    channel_brand = branding.get("channel") or {}
    topic = raw.get("topicDetails") or {}
    from instascope_shared.services.youtube_client import _thumbnails_map

    existing.thumbnails = _thumbnails_map(snippet.get("thumbnails"))
    existing.country = snippet.get("country") or channel_brand.get("country")
    existing.published_at = _parse_yt_datetime(info.published_at or snippet.get("publishedAt"))
    existing.keywords = channel_brand.get("keywords")
    existing.banner_url = image.get("bannerExternalUrl")
    existing.topic_categories = [str(x) for x in (topic.get("topicCategories") or []) if x]
    existing.public_api = raw
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
    """Refresh public channel metrics + programme-window videos + daily snapshot.

    Uses stored channel_id only (no search.list). Videos are limited to uploads
    on/after SPARK_COHORT_START (default 15 Jul 2026). Failures are recorded on
    the YouTubeChannel document; bulk fan-out callers should catch and continue.
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
            "videos_since": cohort_start_ymd(),
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
    floor = cohort_start_dt()
    floor_ymd = cohort_start_ymd()
    cap = _effective_max_videos(max_videos)
    video_ids: list[str] = []
    async for vid in yt.iter_upload_video_ids(
        channel.uploads_playlist_id or "",
        max_videos=cap,
        published_after=floor_ymd,
    ):
        video_ids.append(vid)
    if not video_ids:
        # Drop any pre-programme rows left from older syncs.
        await _purge_videos_before_floor(channel.channel_id, floor)
        return 0

    infos = await yt.list_videos(video_ids)
    now = datetime.utcnow()
    upserted = 0
    kept_ids: set[str] = set()
    for info in infos:
        pub = _parse_yt_datetime(info.published_at)
        if pub is not None and pub.date() < cohort_start_date():
            continue
        existing = await YouTubeVideo.find_one(YouTubeVideo.video_id == info.video_id)
        if not existing:
            existing = YouTubeVideo(
                profile_id=str(profile.id),
                user_id=profile.user_id,
                channel_id=channel.channel_id,
                video_id=info.video_id,
            )
        _apply_video_fields(existing, info, profile=profile, channel=channel)
        existing.updated_at = now
        if existing.id is None:
            await existing.insert()
        else:
            await existing.save()
        kept_ids.add(info.video_id)
        upserted += 1

    await _purge_videos_before_floor(channel.channel_id, floor, keep_ids=kept_ids)
    return upserted


async def _purge_videos_before_floor(
    channel_id: str,
    floor: datetime,
    *,
    keep_ids: set[str] | None = None,
) -> int:
    """Remove stored videos older than programme start."""
    del keep_ids  # reserved for future selective keep; floor is the source of truth
    removed = 0
    async for row in YouTubeVideo.find(YouTubeVideo.channel_id == channel_id):
        pub = row.published_at
        if pub is None:
            continue
        if pub.replace(tzinfo=None) < floor:
            await row.delete()
            removed += 1
    if removed:
        logger.info(
            "purged %s pre-programme YouTube video(s) for channel=%s (floor=%s)",
            removed,
            channel_id,
            floor.date().isoformat(),
        )
    return removed


async def _sum_video_engagement(channel_id: str) -> tuple[int, int]:
    likes = 0
    comments = 0
    floor = cohort_start_dt()
    async for row in YouTubeVideo.find(YouTubeVideo.channel_id == channel_id):
        if row.published_at and row.published_at.replace(tzinfo=None) < floor:
            continue
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


def _video_public_dict(row: YouTubeVideo) -> dict[str, Any]:
    is_short = bool(getattr(row, "is_short", False))
    duration_seconds = getattr(row, "duration_seconds", None)
    if duration_seconds is None and row.duration:
        is_short, duration_seconds = classify_youtube_short(
            duration=row.duration,
            title=row.title,
            description=row.description,
            tags=list(row.tags or []),
        )
    return {
        "video_id": row.video_id,
        "title": row.title,
        "description": row.description or "",
        "url": row.url,
        "published_at": row.published_at.isoformat() + "Z" if row.published_at else None,
        "thumbnail_url": row.thumbnail_url,
        "thumbnails": dict(getattr(row, "thumbnails", None) or {}),
        "channel_title": row.channel_title,
        "tags": list(row.tags or []),
        "category_id": row.category_id,
        "live_broadcast_content": row.live_broadcast_content,
        "default_language": row.default_language,
        "default_audio_language": row.default_audio_language,
        "topic_categories": list(getattr(row, "topic_categories", None) or []),
        "recording_date": getattr(row, "recording_date", None),
        "live_streaming": dict(getattr(row, "live_streaming", None) or {}),
        "player_embed_html": getattr(row, "player_embed_html", None),
        "localizations": dict(getattr(row, "localizations", None) or {}),
        "content_rating": dict(getattr(row, "content_rating", None) or {}),
        "region_restriction": dict(getattr(row, "region_restriction", None) or {}),
        "view_count": int(row.view_count or 0),
        "like_count": row.like_count,
        "comment_count": row.comment_count,
        "favorite_count": row.favorite_count,
        "duration": row.duration,
        "duration_seconds": duration_seconds,
        "is_short": is_short,
        "dimension": row.dimension,
        "definition": row.definition,
        "caption": row.caption,
        "licensed_content": row.licensed_content,
        "projection": row.projection,
        "privacy_status": row.privacy_status,
        "upload_status": row.upload_status,
        "license": row.license,
        "embeddable": row.embeddable,
        "public_stats_viewable": row.public_stats_viewable,
        "made_for_kids": row.made_for_kids,
        "public_api": dict(getattr(row, "public_api", None) or {}),
    }


def _video_is_short(row: YouTubeVideo) -> bool:
    if getattr(row, "is_short", None) is True:
        return True
    if getattr(row, "is_short", None) is False and getattr(row, "duration_seconds", None) is not None:
        return False
    is_short, _ = classify_youtube_short(
        duration=row.duration,
        title=row.title,
        description=row.description,
        tags=list(row.tags or []),
    )
    return is_short


async def get_youtube_insights(profile_id: str) -> dict[str, Any]:
    """Public YouTube data for Insights tab — channel + all videos since programme start."""
    channel = await YouTubeChannel.find_one(YouTubeChannel.profile_id == profile_id)
    floor = cohort_start_dt()
    videos: list[YouTubeVideo] = []
    if channel:
        rows = await YouTubeVideo.find(YouTubeVideo.channel_id == channel.channel_id).sort(
            -YouTubeVideo.published_at
        ).to_list()
        for row in rows:
            if row.published_at and row.published_at.replace(tzinfo=None) < floor:
                continue
            videos.append(row)

    video_dicts = [_video_public_dict(v) for v in videos]
    shorts = [v for v in videos if _video_is_short(v)]
    long_form = [v for v in videos if not _video_is_short(v)]
    views = sum(int(v.view_count or 0) for v in videos)
    likes = sum(int(v.like_count or 0) for v in videos if v.like_count is not None)
    comments = sum(int(v.comment_count or 0) for v in videos if v.comment_count is not None)
    shorts_views = sum(int(v.view_count or 0) for v in shorts)
    long_views = sum(int(v.view_count or 0) for v in long_form)
    best = max(videos, key=lambda v: int(v.view_count or 0), default=None)

    return {
        "connected": bool(channel and channel.connected),
        "window_from": cohort_start_ymd(),
        "window_to": datetime.utcnow().date().isoformat(),
        "channel": None
        if not channel
        else {
            "channel_id": channel.channel_id,
            "channel_url": channel.channel_url,
            "handle": channel.handle,
            "channel_name": channel.channel_name,
            "description": channel.description,
            "thumbnail_url": channel.thumbnail_url,
            "thumbnails": dict(getattr(channel, "thumbnails", None) or {}),
            "country": getattr(channel, "country", None),
            "published_at": channel.published_at.isoformat() + "Z"
            if getattr(channel, "published_at", None)
            else None,
            "keywords": getattr(channel, "keywords", None),
            "banner_url": getattr(channel, "banner_url", None),
            "topic_categories": list(getattr(channel, "topic_categories", None) or []),
            "subscriber_count": channel.subscriber_count,
            "hidden_subscriber_count": channel.hidden_subscriber_count,
            "view_count": channel.view_count,
            "video_count": channel.video_count,
            "sync_status": channel.sync_status.value
            if hasattr(channel.sync_status, "value")
            else str(channel.sync_status),
            "last_error": channel.last_error,
            "last_synced_at": channel.last_synced_at.isoformat() + "Z"
            if channel.last_synced_at
            else None,
            "public_api": dict(getattr(channel, "public_api", None) or {}),
        },
        "totals": {
            "videos_in_window": len(videos),
            "shorts_count": len(shorts),
            "long_form_count": len(long_form),
            "views_in_window": views,
            "shorts_views": shorts_views,
            "long_form_views": long_views,
            "likes_in_window": likes,
            "comments_in_window": comments,
            "avg_views": round(views / len(videos), 1) if videos else 0,
            "best_video_id": best.video_id if best else None,
            "best_video_title": best.title if best else None,
            "best_video_views": int(best.view_count or 0) if best else 0,
        },
        "videos": video_dicts,
    }


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
