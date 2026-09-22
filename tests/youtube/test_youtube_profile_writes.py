"""YouTube syncs must write only their own Profile fields (no DB).

A sync holds its Profile copy for the whole run and used to save() it, which
$sets every field — reverting an Instagram scrape's results or progress, an
edited link, or bonus points written meanwhile. The 08:00 Instagram and
YouTube fan-outs overlap, so this hit daily scrapes too.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_youtube_sync_writes_only_youtube_fields(monkeypatch):
    import instascope_shared.services.youtube_sync as ys

    writes: list[dict] = []

    class _One:
        async def update(self, op):
            writes.append(op["$set"])

    class _Profile:
        id = "id-field"

        @staticmethod
        def find_one(*_args, **_kwargs):
            return _One()

    monkeypatch.setattr(ys, "Profile", _Profile)
    profile = SimpleNamespace(
        id="p1",
        username="stale_handle",
        followers=433,
        scrape_progress={"phase": "saving"},
        youtube_channel_id="UC1",
        youtube_connected=True,
        youtube_last_synced_at=None,
    )

    await ys._save_youtube_refs(profile)

    assert set(writes[0]) == {
        "youtube_channel_id",
        "youtube_connected",
        "youtube_last_synced_at",
        "updated_at",
    }
