"""YouTube Data API v3 client (public data only, server-side API key).

Quota-aware helpers for ~900 participants:
- Resolve handle/URL → channel ID once (prefer channels.list forHandle/id/forUsername).
- Daily sync should use stored channel IDs + uploads playlist + videos.list.
- Avoid search.list except as a last-resort one-time resolution (100 units).

Never log or raise the raw API key.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from instascope_shared.core.config import get_settings
from instascope_shared.services.youtube_errors import (
    YouTubeApiError,
    YouTubeConfigError,
    YouTubeInvalidChannelError,
    YouTubeNotFoundError,
    YouTubeQuotaExceededError,
    YouTubeRateLimitError,
)

logger = logging.getLogger("instascope.youtube.client")

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
# YouTube allows up to 50 ids per channels.list / videos.list call.
MAX_IDS_PER_REQUEST = 50
# All public channel parts available with an API key (no OAuth / Analytics).
CHANNEL_PUBLIC_PARTS = "snippet,statistics,contentDetails,brandingSettings,topicDetails,status"
# All public video parts available with an API key.
VIDEO_PUBLIC_PARTS = (
    "snippet,statistics,contentDetails,status,topicDetails,"
    "recordingDetails,liveStreamingDetails,player,localizations"
)

ChannelRefKind = Literal["channel_id", "handle", "username", "custom_path"]


@dataclass(frozen=True)
class ChannelRef:
    """Parsed user input before / after resolution."""

    kind: ChannelRefKind
    value: str
    raw: str


@dataclass(frozen=True)
class YouTubeChannelInfo:
    channel_id: str
    title: str
    description: str
    custom_url: str | None
    thumbnail_url: str | None
    subscriber_count: int | None
    hidden_subscriber_count: bool
    view_count: int
    video_count: int
    uploads_playlist_id: str | None
    published_at: str | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class YouTubePlaylistItem:
    video_id: str
    title: str
    published_at: str | None
    position: int | None


@dataclass(frozen=True)
class YouTubeVideoInfo:
    video_id: str
    title: str
    description: str
    published_at: str | None
    thumbnail_url: str | None
    channel_id: str | None
    channel_title: str | None
    tags: tuple[str, ...]
    category_id: str | None
    live_broadcast_content: str | None
    default_language: str | None
    default_audio_language: str | None
    view_count: int
    like_count: int | None
    comment_count: int | None
    favorite_count: int | None
    duration: str | None
    dimension: str | None
    definition: str | None
    caption: str | None
    licensed_content: bool | None
    projection: str | None
    privacy_status: str | None
    upload_status: str | None
    license: str | None
    embeddable: bool | None
    public_stats_viewable: bool | None
    made_for_kids: bool | None
    raw: dict[str, Any]


_CHANNEL_ID_RE = re.compile(r"^UC[\w-]{20,}$")
_HANDLE_RE = re.compile(r"^@?[\w.-]{1,100}$", re.UNICODE)


def redact_secrets(text: str, api_key: str | None = None) -> str:
    """Strip API keys from URLs/messages before logging or raising."""
    out = text or ""
    if api_key:
        out = out.replace(api_key, "[REDACTED]")
    out = re.sub(r"([?&]key=)[^&\s]+", r"\1[REDACTED]", out, flags=re.IGNORECASE)
    return out


def parse_channel_input(raw: str) -> ChannelRef:
    """Parse a YouTube URL, @handle, or channel ID into a resolution strategy.

    Supported:
    - UC… channel ID
    - @handle / youtube.com/@handle
    - youtube.com/channel/UCxxx
    - youtube.com/user/USERNAME
    - youtube.com/c/CustomName (one-time resolution may need search later)
    """
    text = (raw or "").strip()
    if not text:
        raise YouTubeInvalidChannelError("Empty YouTube channel URL or handle")

    # Bare channel ID
    if _CHANNEL_ID_RE.match(text):
        return ChannelRef(kind="channel_id", value=text, raw=raw)

    # Bare @handle or handle
    if text.startswith("@") or ("/" not in text and " " not in text and _HANDLE_RE.match(text)):
        handle = text[1:] if text.startswith("@") else text
        if not handle:
            raise YouTubeInvalidChannelError("Empty YouTube handle")
        return ChannelRef(kind="handle", value=handle, raw=raw)

    # URL forms
    url = text
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url.lstrip("/")

    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise YouTubeInvalidChannelError(f"Could not parse YouTube URL: {text}") from exc

    host = (parsed.netloc or "").lower().replace("www.", "")
    if host not in {"youtube.com", "m.youtube.com", "youtu.be", "music.youtube.com"}:
        # Still allow path-like youtube.com without scheme already handled
        if "youtube" not in host and host != "youtu.be":
            raise YouTubeInvalidChannelError(f"Not a YouTube URL: {text}")

    path = unquote(parsed.path or "").strip("/")
    parts = [p for p in path.split("/") if p]

    if not parts:
        # ?channel_id= / ?ab_channel=
        qs = parse_qs(parsed.query or "")
        for key in ("channel_id", "channelid"):
            if qs.get(key):
                cid = qs[key][0]
                if _CHANNEL_ID_RE.match(cid):
                    return ChannelRef(kind="channel_id", value=cid, raw=raw)
        raise YouTubeInvalidChannelError(f"Could not find channel in URL: {text}")

    head = parts[0].lower()

    if head == "channel" and len(parts) >= 2:
        cid = parts[1]
        if not _CHANNEL_ID_RE.match(cid):
            raise YouTubeInvalidChannelError(f"Invalid channel ID in URL: {cid}")
        return ChannelRef(kind="channel_id", value=cid, raw=raw)

    if head == "user" and len(parts) >= 2:
        return ChannelRef(kind="username", value=parts[1], raw=raw)

    if head in {"c", "custom"} and len(parts) >= 2:
        return ChannelRef(kind="custom_path", value=parts[1], raw=raw)

    if parts[0].startswith("@"):
        return ChannelRef(kind="handle", value=parts[0][1:], raw=raw)

    # youtu.be does not identify channels — reject
    if host == "youtu.be":
        raise YouTubeInvalidChannelError(
            "youtu.be video links are not channel URLs; use /@handle or /channel/UC…"
        )

    raise YouTubeInvalidChannelError(f"Unsupported YouTube channel URL: {text}")


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _as_optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _strip_api_html(message: str) -> str:
    """YouTube sometimes embeds <code>…</code> in error messages."""
    cleaned = re.sub(r"</?code>", "", message or "")
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    return cleaned.strip()


def uploads_playlist_id_for_channel(
    channel_id: str | None,
    reported: str | None = None,
) -> str | None:
    """Resolve uploads playlist id (UU…) from API value or UC→UU convention.

    Never treat a bare channel id (UC…) as a playlist id — playlistItems.list
    will 404 with "playlistId parameter cannot be found".
    """
    reported = str(reported or "").strip()
    cid = str(channel_id or "").strip()
    if reported.startswith("UU"):
        return reported
    if reported and not reported.startswith("UC"):
        return reported
    if cid.startswith("UC") and len(cid) > 2:
        return "UU" + cid[2:]
    if reported.startswith("UC") and len(reported) > 2:
        return "UU" + reported[2:]
    return reported or None


def _thumbnails_map(thumbs: dict[str, Any] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if not isinstance(thumbs, dict):
        return out
    for key, row in thumbs.items():
        if isinstance(row, dict) and row.get("url"):
            out[str(key)] = str(row["url"])
    return out


def _best_thumb(thumbs: dict[str, Any] | None) -> str | None:
    mapped = _thumbnails_map(thumbs)
    for key in ("maxres", "standard", "high", "medium", "default"):
        if key in mapped:
            return mapped[key]
    return next(iter(mapped.values()), None)


def _channel_from_item(item: dict[str, Any]) -> YouTubeChannelInfo:
    snippet = item.get("snippet") or {}
    stats = item.get("statistics") or {}
    content = item.get("contentDetails") or {}
    related = content.get("relatedPlaylists") or {}
    thumb = _best_thumb(snippet.get("thumbnails"))
    hidden = bool(stats.get("hiddenSubscriberCount"))
    subs = None if hidden else _as_optional_int(stats.get("subscriberCount"))
    channel_id = str(item.get("id") or "")
    return YouTubeChannelInfo(
        channel_id=channel_id,
        title=str(snippet.get("title") or ""),
        description=str(snippet.get("description") or ""),
        custom_url=snippet.get("customUrl"),
        thumbnail_url=thumb,
        subscriber_count=subs,
        hidden_subscriber_count=hidden,
        view_count=_as_int(stats.get("viewCount")),
        video_count=_as_int(stats.get("videoCount")),
        uploads_playlist_id=uploads_playlist_id_for_channel(
            channel_id, related.get("uploads")
        ),
        published_at=snippet.get("publishedAt"),
        raw=item,
    )


def _video_from_item(item: dict[str, Any]) -> YouTubeVideoInfo:
    snippet = item.get("snippet") or {}
    stats = item.get("statistics") or {}
    content = item.get("contentDetails") or {}
    status = item.get("status") or {}
    thumb = _best_thumb(snippet.get("thumbnails"))
    tags_raw = snippet.get("tags") or []
    tags = tuple(str(t) for t in tags_raw if t) if isinstance(tags_raw, list) else ()
    return YouTubeVideoInfo(
        video_id=str(item.get("id") or ""),
        title=str(snippet.get("title") or ""),
        description=str(snippet.get("description") or ""),
        published_at=snippet.get("publishedAt"),
        thumbnail_url=thumb,
        channel_id=snippet.get("channelId"),
        channel_title=snippet.get("channelTitle"),
        tags=tags,
        category_id=str(snippet["categoryId"]) if snippet.get("categoryId") is not None else None,
        live_broadcast_content=snippet.get("liveBroadcastContent"),
        default_language=snippet.get("defaultLanguage"),
        default_audio_language=snippet.get("defaultAudioLanguage"),
        view_count=_as_int(stats.get("viewCount")),
        like_count=_as_optional_int(stats.get("likeCount")),
        comment_count=_as_optional_int(stats.get("commentCount")),
        favorite_count=_as_optional_int(stats.get("favoriteCount")),
        duration=content.get("duration"),
        dimension=content.get("dimension"),
        definition=content.get("definition"),
        caption=content.get("caption"),
        licensed_content=content.get("licensedContent"),
        projection=content.get("projection"),
        privacy_status=status.get("privacyStatus"),
        upload_status=status.get("uploadStatus"),
        license=status.get("license"),
        embeddable=status.get("embeddable"),
        public_stats_viewable=status.get("publicStatsViewable"),
        made_for_kids=status.get("madeForKids"),
        raw=item,
    )


def chunked(values: list[str], size: int = MAX_IDS_PER_REQUEST) -> list[list[str]]:
    clean = [v for v in values if v]
    return [clean[i : i + size] for i in range(0, len(clean), size)]


class YouTubeClient:
    """Thin async client around YouTube Data API v3 (API key auth)."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        timeout: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ):
        key = (api_key if api_key is not None else get_settings().youtube_api_key) or ""
        key = key.strip()
        if not key:
            raise YouTubeConfigError(
                "YOUTUBE_API_KEY is not configured. Set it in the server .env "
                "(never in frontend or git)."
            )
        self._api_key = key
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=YOUTUBE_API_BASE,
            timeout=timeout,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> YouTubeClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    def __repr__(self) -> str:
        return "YouTubeClient(api_key=[REDACTED])"

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        # key only in query params object — never log params with key
        safe_params = {k: v for k, v in params.items() if k != "key"}
        req_params = {**params, "key": self._api_key}
        try:
            resp = await self._client.get(path, params=req_params)
        except httpx.HTTPError as exc:
            msg = redact_secrets(str(exc), self._api_key)
            logger.warning("YouTube network error path=%s err=%s", path, msg)
            raise YouTubeApiError(f"YouTube network error: {msg}", reason="network") from exc

        body: dict[str, Any]
        try:
            body = resp.json()
        except Exception:
            body = {}

        if resp.status_code == 200:
            return body

        err = (body.get("error") or {}) if isinstance(body, dict) else {}
        message = _strip_api_html(
            redact_secrets(str(err.get("message") or resp.text or "YouTube API error"), self._api_key)
        )
        reason = ""
        for e in err.get("errors") or []:
            if isinstance(e, dict) and e.get("reason"):
                reason = str(e["reason"])
                break

        logger.warning(
            "YouTube API error status=%s reason=%s path=%s params=%s msg=%s",
            resp.status_code,
            reason or "-",
            path,
            safe_params,
            message[:300],
        )

        if reason in {"quotaExceeded", "dailyLimitExceeded"} or (
            resp.status_code == 403 and "quota" in message.lower()
        ):
            raise YouTubeQuotaExceededError(message)
        if resp.status_code == 429 or reason in {"rateLimitExceeded", "userRateLimitExceeded"}:
            raise YouTubeRateLimitError(message)
        if resp.status_code == 404 or reason in {"channelNotFound", "playlistNotFound", "videoNotFound"}:
            if reason == "playlistNotFound" or "playlistid" in message.lower():
                raise YouTubeNotFoundError(
                    "YouTube uploads playlist not found (channel may have no public videos)",
                    reason="playlistNotFound",
                )
            raise YouTubeNotFoundError(message, reason=reason or "not_found")
        raise YouTubeApiError(message, status_code=resp.status_code, reason=reason or "api_error")

    async def list_channels_by_ids(self, channel_ids: list[str]) -> list[YouTubeChannelInfo]:
        """channels.list?id=… (batched, ≤50 ids). Cost: 1 unit per call."""
        out: list[YouTubeChannelInfo] = []
        for batch in chunked(channel_ids):
            data = await self._get(
                "/channels",
                {
                    "part": CHANNEL_PUBLIC_PARTS,
                    "id": ",".join(batch),
                    "maxResults": MAX_IDS_PER_REQUEST,
                },
            )
            for item in data.get("items") or []:
                info = _channel_from_item(item)
                if info.channel_id:
                    out.append(info)
        return out

    async def get_channel_by_id(self, channel_id: str) -> YouTubeChannelInfo:
        rows = await self.list_channels_by_ids([channel_id])
        if not rows:
            raise YouTubeNotFoundError(f"YouTube channel not found: {channel_id}")
        return rows[0]

    async def get_channel_by_handle(self, handle: str) -> YouTubeChannelInfo:
        """channels.list?forHandle=… (1 unit). Prefer over search.list."""
        handle = handle.lstrip("@").strip()
        data = await self._get(
            "/channels",
            {
                "part": CHANNEL_PUBLIC_PARTS,
                "forHandle": handle,
            },
        )
        items = data.get("items") or []
        if not items:
            raise YouTubeNotFoundError(f"YouTube handle not found: @{handle}")
        return _channel_from_item(items[0])

    async def get_channel_by_username(self, username: str) -> YouTubeChannelInfo:
        """channels.list?forUsername=… (legacy /user/USERNAME)."""
        data = await self._get(
            "/channels",
            {
                "part": CHANNEL_PUBLIC_PARTS,
                "forUsername": username,
            },
        )
        items = data.get("items") or []
        if not items:
            raise YouTubeNotFoundError(f"YouTube username not found: {username}")
        return _channel_from_item(items[0])

    async def search_channel_once(self, query: str) -> YouTubeChannelInfo:
        """LAST RESORT one-time resolution via search.list (100 units).

        Do not call this on daily sync paths.
        """
        logger.warning(
            "YouTube search.list used for one-time channel resolve query=%r (100 quota units)",
            query[:80],
        )
        data = await self._get(
            "/search",
            {
                "part": "snippet",
                "q": query,
                "type": "channel",
                "maxResults": 1,
            },
        )
        items = data.get("items") or []
        if not items:
            raise YouTubeNotFoundError(f"No YouTube channel matched: {query}")
        channel_id = (items[0].get("snippet") or {}).get("channelId") or items[0].get("id", {}).get(
            "channelId"
        )
        if not channel_id:
            raise YouTubeNotFoundError(f"No YouTube channel id in search result for: {query}")
        return await self.get_channel_by_id(str(channel_id))

    async def resolve_channel(self, raw: str, *, allow_search: bool = True) -> YouTubeChannelInfo:
        """Resolve URL/handle to full channel info; store channel_id permanently after this."""
        ref = parse_channel_input(raw)
        if ref.kind == "channel_id":
            return await self.get_channel_by_id(ref.value)
        if ref.kind == "handle":
            return await self.get_channel_by_handle(ref.value)
        if ref.kind == "username":
            return await self.get_channel_by_username(ref.value)
        if ref.kind == "custom_path":
            if not allow_search:
                raise YouTubeInvalidChannelError(
                    f"Custom path /c/{ref.value} needs one-time search; pass allow_search=True"
                )
            return await self.search_channel_once(ref.value)
        raise YouTubeInvalidChannelError(f"Unsupported channel ref: {ref.kind}")

    async def list_playlist_items(
        self,
        playlist_id: str,
        *,
        page_token: str | None = None,
        max_results: int = 50,
        channel_id: str | None = None,
    ) -> tuple[list[YouTubePlaylistItem], str | None]:
        """playlistItems.list for uploads playlist (1 unit per page)."""
        pid = str(playlist_id or "").strip()
        fallback = uploads_playlist_id_for_channel(channel_id, pid)
        # Prefer derived UU… when reported id looks like a channel id
        if fallback and fallback != pid and pid.startswith("UC"):
            pid = fallback

        params: dict[str, Any] = {
            "part": "snippet,contentDetails",
            "playlistId": pid,
            "maxResults": max(1, min(50, max_results)),
        }
        if page_token:
            params["pageToken"] = page_token
        try:
            data = await self._get("/playlistItems", params)
        except YouTubeNotFoundError as exc:
            alt = uploads_playlist_id_for_channel(channel_id, None)
            if (
                getattr(exc, "reason", "") == "playlistNotFound"
                and alt
                and alt != pid
                and not page_token
            ):
                params = {**params, "playlistId": alt}
                data = await self._get("/playlistItems", params)
            else:
                raise
        items: list[YouTubePlaylistItem] = []
        for item in data.get("items") or []:
            content = item.get("contentDetails") or {}
            snippet = item.get("snippet") or {}
            video_id = content.get("videoId") or (snippet.get("resourceId") or {}).get("videoId")
            if not video_id:
                continue
            items.append(
                YouTubePlaylistItem(
                    video_id=str(video_id),
                    title=str(snippet.get("title") or ""),
                    published_at=content.get("videoPublishedAt") or snippet.get("publishedAt"),
                    position=snippet.get("position"),
                )
            )
        return items, data.get("nextPageToken")

    async def iter_upload_video_ids(
        self,
        uploads_playlist_id: str,
        *,
        max_videos: int | None = None,
        published_after: str | None = None,
        channel_id: str | None = None,
    ):
        """Paginate uploads playlist (newest first); yields video IDs.

        If ``published_after`` is set (RFC3339 or YYYY-MM-DD), stop when a page
        item is older than that floor (programme window). Uploads playlists are
        reverse-chronological, so older videos are not fetched.
        """
        from datetime import datetime as _dt

        floor: _dt | None = None
        if published_after:
            raw = published_after.strip()
            try:
                if len(raw) == 10 and raw[4] == "-":
                    floor = _dt.fromisoformat(raw)
                else:
                    floor = _dt.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                floor = None

        token: str | None = None
        yielded = 0
        while True:
            page, token = await self.list_playlist_items(
                uploads_playlist_id,
                page_token=token,
                channel_id=channel_id,
            )
            if not page:
                if not token:
                    return
                continue
            new_on_page = 0
            for row in page:
                is_old = False
                if floor is not None and row.published_at:
                    try:
                        pub = _dt.fromisoformat(
                            str(row.published_at).replace("Z", "+00:00")
                        ).replace(tzinfo=None)
                        is_old = pub.date() < floor.date()
                    except Exception:
                        is_old = False
                if is_old:
                    continue
                yield row.video_id
                yielded += 1
                new_on_page += 1
                if max_videos is not None and yielded >= max_videos:
                    return
            # Uploads are usually newest-first. Stop only when a whole page is
            # older than the programme floor — one stale/misdated item must not
            # freeze the count while later videos still exist.
            if floor is not None and new_on_page == 0:
                return
            if not token:
                return

    async def list_videos(self, video_ids: list[str]) -> list[YouTubeVideoInfo]:
        """videos.list?id=… batched ≤50 (1 unit per call). Public parts only."""
        out: list[YouTubeVideoInfo] = []
        for batch in chunked(video_ids):
            data = await self._get(
                "/videos",
                {
                    "part": VIDEO_PUBLIC_PARTS,
                    "id": ",".join(batch),
                    "maxResults": MAX_IDS_PER_REQUEST,
                },
            )
            for item in data.get("items") or []:
                info = _video_from_item(item)
                if info.video_id:
                    out.append(info)
        return out
