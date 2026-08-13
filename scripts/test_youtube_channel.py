#!/usr/bin/env python3
"""Manually test ONE YouTube channel resolve+sync (does not run the 900-user fan-out).

Usage (from repo root, with YOUTUBE_API_KEY in .env):

  python scripts/test_youtube_channel.py --url "https://www.youtube.com/@GoogleDevelopers"
  python scripts/test_youtube_channel.py --url "@GoogleDevelopers" --resolve-only

Optional: --profile-id <mongo Profile id> to persist into MongoDB.
Without --profile-id, only resolves via API and prints public metrics (no DB write).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "python-shared"))


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


async def _resolve_only(url: str) -> dict:
    from instascope_shared.services.youtube_client import YouTubeClient

    async with YouTubeClient() as yt:
        info = await yt.resolve_channel(url, allow_search=True)
        return {
            "channel_id": info.channel_id,
            "title": info.title,
            "handle": info.custom_url,
            "subscribers": info.subscriber_count,
            "views": info.view_count,
            "videos": info.video_count,
            "uploads_playlist_id": info.uploads_playlist_id,
            "thumbnail": info.thumbnail_url,
        }


async def _sync_profile(profile_id: str, url: str | None, max_videos: int) -> dict:
    from instascope_shared.db.mongodb import close_db, connect_db
    from instascope_shared.models import Profile
    from instascope_shared.services.youtube_sync import connect_youtube_channel, sync_youtube_channel

    await connect_db()
    try:
        profile = await Profile.get(profile_id)
        if not profile:
            raise SystemExit(f"Profile not found: {profile_id}")
        if url:
            return await connect_youtube_channel(profile, url, max_videos=max_videos)
        return await sync_youtube_channel(profile_id, max_videos=max_videos)
    finally:
        await close_db()


def main() -> None:
    _load_dotenv()
    parser = argparse.ArgumentParser(description="Test one YouTube channel (quota-safe)")
    parser.add_argument("--url", help="Channel URL, @handle, or UC… id")
    parser.add_argument("--profile-id", help="Mongo Profile ObjectId to persist into")
    parser.add_argument("--resolve-only", action="store_true", help="API resolve only, no Mongo writes")
    parser.add_argument("--max-videos", type=int, default=10, help="Max uploads to fetch (default 10)")
    args = parser.parse_args()

    if not os.getenv("YOUTUBE_API_KEY", "").strip():
        raise SystemExit(
            "YOUTUBE_API_KEY is not set. Add it to your local/production .env "
            "(never commit it; never put it in NEXT_PUBLIC_*)."
        )

    if args.resolve_only or not args.profile_id:
        if not args.url:
            raise SystemExit("--url is required for resolve-only / no-profile mode")
        data = asyncio.run(_resolve_only(args.url))
    else:
        data = asyncio.run(_sync_profile(args.profile_id, args.url, args.max_videos))

    print(json.dumps(data, indent=2, default=str))


if __name__ == "__main__":
    main()
