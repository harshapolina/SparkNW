"""Stage 1 tests: YouTube client config, parsing, and mocked API calls.

Does not require a real YOUTUBE_API_KEY.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from instascope_shared.services.youtube_client import (
    YouTubeClient,
    parse_channel_input,
    redact_secrets,
)
from instascope_shared.services.youtube_errors import (
    YouTubeConfigError,
    YouTubeInvalidChannelError,
    YouTubeNotFoundError,
    YouTubeQuotaExceededError,
)


def test_redact_secrets_strips_key_from_url():
    key = "AIzaSyFakeKeyForTestsOnly1234567890"
    text = f"https://www.googleapis.com/youtube/v3/channels?key={key}&part=snippet"
    out = redact_secrets(text, key)
    assert key not in out
    assert "[REDACTED]" in out


def test_parse_channel_id():
    ref = parse_channel_input("UCabcdefghijklmnopqrstuv")
    assert ref.kind == "channel_id"
    assert ref.value.startswith("UC")


def test_parse_handle_bare_and_at():
    assert parse_channel_input("@MrBeast").kind == "handle"
    assert parse_channel_input("@MrBeast").value == "MrBeast"
    assert parse_channel_input("MrBeast").kind == "handle"


def test_parse_channel_url():
    ref = parse_channel_input("https://www.youtube.com/channel/UCabcdefghijklmnopqrstuv")
    assert ref.kind == "channel_id"
    assert ref.value == "UCabcdefghijklmnopqrstuv"


def test_parse_at_handle_url():
    ref = parse_channel_input("https://youtube.com/@SomeCreator")
    assert ref.kind == "handle"
    assert ref.value == "SomeCreator"


def test_parse_user_url():
    ref = parse_channel_input("https://www.youtube.com/user/LegacyName")
    assert ref.kind == "username"
    assert ref.value == "LegacyName"


def test_parse_custom_path():
    ref = parse_channel_input("https://www.youtube.com/c/CustomBrand")
    assert ref.kind == "custom_path"
    assert ref.value == "CustomBrand"


def test_parse_empty_and_invalid():
    with pytest.raises(YouTubeInvalidChannelError):
        parse_channel_input("")
    with pytest.raises(YouTubeInvalidChannelError):
        parse_channel_input("https://example.com/foo")
    with pytest.raises(YouTubeInvalidChannelError):
        parse_channel_input("https://youtu.be/dQw4w9WgXcQ")


def test_client_requires_api_key(monkeypatch):
    from instascope_shared.core import config as cfg

    cfg.get_settings.cache_clear()

    class _Empty:
        youtube_api_key = None

    monkeypatch.setattr(cfg, "get_settings", lambda: _Empty())
    with pytest.raises(YouTubeConfigError):
        YouTubeClient(api_key=None)
    with pytest.raises(YouTubeConfigError):
        YouTubeClient(api_key="   ")


def test_client_repr_hides_key():
    client = YouTubeClient(api_key="AIzaSySecretShouldNeverAppear")
    assert "Secret" not in repr(client)
    assert "[REDACTED]" in repr(client)


def _mock_response(status: int, payload: dict) -> httpx.Response:
    return httpx.Response(
        status_code=status,
        json=payload,
        request=httpx.Request("GET", "https://www.googleapis.com/youtube/v3/channels"),
    )


@pytest.mark.asyncio
async def test_get_channel_by_id_success():
    channel_id = "UCabcdefghijklmnopqrstuv"
    payload = {
        "items": [
            {
                "id": channel_id,
                "snippet": {
                    "title": "Demo Channel",
                    "description": "Hi",
                    "customUrl": "@demo",
                    "thumbnails": {"default": {"url": "https://img.example/t.jpg"}},
                    "publishedAt": "2020-01-01T00:00:00Z",
                },
                "statistics": {
                    "viewCount": "1000",
                    "subscriberCount": "50",
                    "hiddenSubscriberCount": False,
                    "videoCount": "3",
                },
                "contentDetails": {"relatedPlaylists": {"uploads": "UU" + channel_id[2:]}},
            }
        ]
    }
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=_mock_response(200, payload))
    client = YouTubeClient(api_key="test-key", client=mock)
    info = await client.get_channel_by_id(channel_id)
    assert info.channel_id == channel_id
    assert info.title == "Demo Channel"
    assert info.subscriber_count == 50
    assert info.view_count == 1000
    assert info.video_count == 3
    assert info.uploads_playlist_id.startswith("UU")
    # Ensure key was passed but we don't assert its value in logs
    args, kwargs = mock.get.await_args
    assert kwargs["params"]["key"] == "test-key"
    assert "test-key" not in repr(client)


@pytest.mark.asyncio
async def test_get_channel_by_id_not_found():
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=_mock_response(200, {"items": []}))
    client = YouTubeClient(api_key="test-key", client=mock)
    with pytest.raises(YouTubeNotFoundError):
        await client.get_channel_by_id("UCabcdefghijklmnopqrstuv")


@pytest.mark.asyncio
async def test_quota_exceeded_maps_error():
    mock = AsyncMock()
    mock.get = AsyncMock(
        return_value=_mock_response(
            403,
            {
                "error": {
                    "message": "The request cannot be completed because you have exceeded your quota.",
                    "errors": [{"reason": "quotaExceeded"}],
                }
            },
        )
    )
    client = YouTubeClient(api_key="test-key", client=mock)
    with pytest.raises(YouTubeQuotaExceededError):
        await client.get_channel_by_id("UCabcdefghijklmnopqrstuv")


@pytest.mark.asyncio
async def test_list_videos_batches():
    # 51 ids → 2 calls
    ids = [f"vid{i:03d}" for i in range(51)]
    call_count = {"n": 0}

    async def fake_get(path, params):
        call_count["n"] += 1
        batch = params["id"].split(",")
        items = [
            {
                "id": vid,
                "snippet": {"title": vid, "description": "", "channelId": "UCx", "thumbnails": {}},
                "statistics": {"viewCount": "1", "likeCount": "2", "commentCount": "3"},
                "contentDetails": {"duration": "PT1M"},
            }
            for vid in batch
        ]
        return _mock_response(200, {"items": items})

    mock = AsyncMock()
    mock.get = AsyncMock(side_effect=fake_get)
    client = YouTubeClient(api_key="test-key", client=mock)
    videos = await client.list_videos(ids)
    assert len(videos) == 51
    assert call_count["n"] == 2
    assert videos[0].like_count == 2


@pytest.mark.asyncio
async def test_resolve_handle_uses_for_handle_not_search():
    mock = AsyncMock()
    mock.get = AsyncMock(
        return_value=_mock_response(
            200,
            {
                "items": [
                    {
                        "id": "UCabcdefghijklmnopqrstuv",
                        "snippet": {"title": "H", "description": "", "thumbnails": {}},
                        "statistics": {
                            "viewCount": "0",
                            "subscriberCount": "1",
                            "hiddenSubscriberCount": False,
                            "videoCount": "0",
                        },
                        "contentDetails": {"relatedPlaylists": {"uploads": "UUabcdefghijklmnopqrstuv"}},
                    }
                ]
            },
        )
    )
    client = YouTubeClient(api_key="test-key", client=mock)
    info = await client.resolve_channel("@SomeCreator", allow_search=False)
    assert info.channel_id.startswith("UC")
    args, kwargs = mock.get.await_args
    assert kwargs["params"].get("forHandle") == "SomeCreator"
    assert "q" not in kwargs["params"]


@pytest.mark.asyncio
async def test_playlist_items_pagination_token():
    mock = AsyncMock()
    mock.get = AsyncMock(
        return_value=_mock_response(
            200,
            {
                "nextPageToken": "NEXT",
                "items": [
                    {
                        "snippet": {
                            "title": "V1",
                            "position": 0,
                            "resourceId": {"videoId": "abc"},
                        },
                        "contentDetails": {"videoId": "abc", "videoPublishedAt": "2024-01-01T00:00:00Z"},
                    }
                ],
            },
        )
    )
    client = YouTubeClient(api_key="test-key", client=mock)
    items, token = await client.list_playlist_items("UUabcdefghijklmnopqrstuv")
    assert len(items) == 1
    assert items[0].video_id == "abc"
    assert token == "NEXT"
