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
    view_count: int
    like_count: int | None
    comment_count: int | None
    duration: str | None
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


def _channel_from_item(item: dict[str, Any]) -> YouTubeChannelInfo:
    snippet = item.get("snippet") or {}
    stats = item.get("statistics") or {}
    content = item.get("contentDetails") or {}
    related = content.get("relatedPlaylists") or {}
    thumbs = snippet.get("thumbnails") or {}
    thumb = (
        (thumbs.get("high") or {}).get("url")
        or (thumbs.get("medium") or {}).get("url")
        or (thumbs.get("default") or {}).get("url")
    )
    hidden = bool(stats.get("hiddenSubscriberCount"))
    subs = None if hidden else _as_optional_int(stats.get("subscriberCount"))
    return YouTubeChannelInfo(
        channel_id=str(item.get("id") or ""),
        title=str(snippet.get("title") or ""),
        description=str(snippet.get("description") or ""),
        custom_url=snippet.get("customUrl"),
        thumbnail_url=thumb,
        subscriber_count=subs,
        hidden_subscriber_count=hidden,
        view_count=_as_int(stats.get("viewCount")),
        video_count=_as_int(stats.get("videoCount")),
        uploads_playlist_id=related.get("uploads"),
        published_at=snippet.get("publishedAt"),
        raw=item,
    )


def _video_from_item(item: dict[str, Any]) -> YouTubeVideoInfo:
    snippet = item.get("snippet") or {}
    stats = item.get("statistics") or {}
    content = item.get("contentDetails") or {}
    thumbs = snippet.get("thumbnails") or {}
    thumb = (
        (thumbs.get("high") or {}).get("url")
        or (thumbs.get("medium") or {}).get("url")
        or (thumbs.get("default") or {}).get("url")
    )
    return YouTubeVideoInfo(
        video_id=str(item.get("id") or ""),
        title=str(snippet.get("title") or ""),
        description=str(snippet.get("description") or ""),
        published_at=snippet.get("publishedAt"),
        thumbnail_url=thumb,
        channel_id=snippet.get("channelId"),
        view_count=_as_int(stats.get("viewCount")),
        like_count=_as_optional_int(stats.get("likeCount")),
        comment_count=_as_optional_int(stats.get("commentCount")),
        duration=content.get("duration"),
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
        message = redact_secrets(str(err.get("message") or resp.text or "YouTube API error"), self._api_key)
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
            raise YouTubeNotFoundError(message)
        raise YouTubeApiError(message, status_code=resp.status_code, reason=reason or "api_error")

    async def list_channels_by_ids(self, channel_ids: list[str]) -> list[YouTubeChannelInfo]:
        """channels.list?id=… (batched, ≤50 ids). Cost: 1 unit per call."""
        out: list[YouTubeChannelInfo] = []
        for batch in chunked(channel_ids):
            data = await self._get(
                "/channels",
                {
                    "part": "snippet,statistics,contentDetails",
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
                "part": "snippet,statistics,contentDetails",
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
                "part": "snippet,statistics,contentDetails",
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
    ) -> tuple[list[YouTubePlaylistItem], str | None]:
        """playlistItems.list for uploads playlist (1 unit per page)."""
        params: dict[str, Any] = {
            "part": "snippet,contentDetails",
            "playlistId": playlist_id,
            "maxResults": max(1, min(50, max_results)),
        }
        if page_token:
            params["pageToken"] = page_token
        data = await self._get("/playlistItems", params)
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
    ):
        """Paginate uploads playlist; yields video IDs."""
        token: str | None = None
        yielded = 0
        while True:
            page, token = await self.list_playlist_items(uploads_playlist_id, page_token=token)
            for row in page:
                yield row.video_id
                yielded += 1
                if max_videos is not None and yielded >= max_videos:
                    return
            if not token:
                return

    async def list_videos(self, video_ids: list[str]) -> list[YouTubeVideoInfo]:
        """videos.list?id=… batched ≤50 (1 unit per call)."""
        out: list[YouTubeVideoInfo] = []
        for batch in chunked(video_ids):
            data = await self._get(
                "/videos",
                {
                    "part": "snippet,statistics,contentDetails",
                    "id": ",".join(batch),
                    "maxResults": MAX_IDS_PER_REQUEST,
                },
            )
            for item in data.get("items") or []:
                info = _video_from_item(item)
                if info.video_id:
                    out.append(info)
        return out
