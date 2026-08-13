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


def test_sync_status_values():
    assert YouTubeSyncStatus.SUCCESS.value == "success"
    assert YouTubeSyncStatus.QUOTA_EXCEEDED.value == "quota_exceeded"


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


def test_document_models_register_youtube():
    from instascope_shared.models import DOCUMENT_MODELS

    names = {getattr(m, "Settings", None) and m.Settings.name for m in DOCUMENT_MODELS}
    assert "youtube_channels" in names
    assert "youtube_videos" in names
    assert "youtube_snapshots" in names
    assert "profiles" in names
