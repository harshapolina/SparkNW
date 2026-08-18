"""Stage 2–4 tests: YouTube models import + sync helpers (mocked API, no real key)."""

from __future__ import annotations

import pytest

from instascope_shared.models import (
    JobType,
    YouTubeChannel,
    YouTubeSnapshot,
    YouTubeSyncStatus,
    YouTubeVideo,
)
from instascope_shared.services.youtube_errors import (
    YouTubeNotFoundError,
    YouTubeQuotaExceededError,
)
from instascope_shared.services.youtube_sync import _map_sync_error, _parse_yt_datetime


def test_job_type_includes_sync_youtube():
    assert JobType.SYNC_YOUTUBE.value == "sync_youtube"


def test_youtube_model_collection_names():
    assert YouTubeChannel.Settings.name == "youtube_channels"
    assert YouTubeVideo.Settings.name == "youtube_videos"
    assert YouTubeSnapshot.Settings.name == "youtube_snapshots"


def test_channel_already_synced():
    from datetime import datetime
    from types import SimpleNamespace

    from instascope_shared.services.youtube_jobs import channel_already_synced

    done = SimpleNamespace(
        last_synced_at=datetime(2026, 8, 14),
        sync_status=YouTubeSyncStatus.SUCCESS,
    )
    assert channel_already_synced(done) is True

    never = SimpleNamespace(last_synced_at=None, sync_status=YouTubeSyncStatus.PENDING)
    assert channel_already_synced(never) is False

    failed = SimpleNamespace(
        last_synced_at=datetime(2026, 8, 14),
        sync_status=YouTubeSyncStatus.FAILED,
    )
    assert channel_already_synced(failed) is False


def test_parse_yt_datetime():
    dt = _parse_yt_datetime("2024-06-01T12:30:00Z")
    assert dt is not None
    assert dt.year == 2024
    assert _parse_yt_datetime(None) is None


def test_map_sync_error_quota_and_not_found():
    status, msg = _map_sync_error(YouTubeQuotaExceededError("quota blown"))
    assert status == YouTubeSyncStatus.QUOTA_EXCEEDED
    assert "quota" in msg.lower()

    status, msg = _map_sync_error(YouTubeNotFoundError("gone"))
    assert status == YouTubeSyncStatus.UNAVAILABLE


def test_uploads_playlist_id_for_channel():
    from instascope_shared.services.youtube_client import uploads_playlist_id_for_channel

    cid = "UCabcdefghijklmnopqrstuv"
    assert uploads_playlist_id_for_channel(cid, "UU" + cid[2:]) == "UU" + cid[2:]
    # Never use bare UC… as playlist id
    assert uploads_playlist_id_for_channel(cid, cid) == "UU" + cid[2:]
    assert uploads_playlist_id_for_channel(cid, None) == "UU" + cid[2:]
    assert uploads_playlist_id_for_channel(cid, "") == "UU" + cid[2:]


def test_is_playlist_not_found():
    from instascope_shared.services.youtube_sync import _is_playlist_not_found

    assert _is_playlist_not_found(
        YouTubeNotFoundError("x", reason="playlistNotFound")
    )
    assert _is_playlist_not_found(
        YouTubeNotFoundError("The playlist identified cannot be found")
    )
    assert not _is_playlist_not_found(YouTubeNotFoundError("channel gone"))


def test_document_models_register_youtube():
    from instascope_shared.models import DOCUMENT_MODELS

    names = {getattr(m, "Settings", None) and m.Settings.name for m in DOCUMENT_MODELS}
    assert "youtube_channels" in names
    assert "youtube_videos" in names
    assert "youtube_snapshots" in names
    assert "spark_top10_snapshots" in names
    assert "profiles" in names
