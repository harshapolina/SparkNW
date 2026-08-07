"""Recover Instagram post timestamps from media id / shortcode when scrape omits taken_at."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# Instagram snowflake epoch (ms) — see Instagram engineering "Sharding IDs"
_IG_EPOCH_MS = 1_314_220_021_721
_IG_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"


def shortcode_to_media_id(shortcode: str | None) -> int | None:
    if not shortcode:
        return None
    code = str(shortcode).strip().rstrip("/")
    if not code or any(c not in _IG_ALPHABET for c in code):
        return None
    n = 0
    try:
        for ch in code:
            n = n * 64 + _IG_ALPHABET.index(ch)
    except ValueError:
        return None
    return n if n > 0 else None


def media_id_to_datetime(media_id: int | str | None) -> datetime | None:
    if media_id is None or media_id == "":
        return None
    try:
        mid = int(str(media_id).split("_")[0])
    except (TypeError, ValueError):
        return None
    if mid <= 0:
        return None
    # Upper 41 bits = ms since Instagram epoch
    ms = (mid >> 23) + _IG_EPOCH_MS
    # Sanity: 2011 … ~2035
    if ms < _IG_EPOCH_MS or ms > 2_500_000_000_000:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
    except (OSError, OverflowError, ValueError):
        return None


def infer_posted_at(
    *,
    posted_at: Any = None,
    shortcode: str | None = None,
    ig_post_id: str | None = None,
) -> datetime | None:
    """Prefer explicit posted_at; else decode from numeric media id or shortcode."""
    if isinstance(posted_at, datetime):
        return posted_at if posted_at.tzinfo else posted_at.replace(tzinfo=timezone.utc)
    if posted_at:
        try:
            raw = str(posted_at).replace("Z", "+00:00")
            dt = datetime.fromisoformat(raw)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    for candidate in (ig_post_id, None):
        if candidate and str(candidate).isdigit():
            dt = media_id_to_datetime(candidate)
            if dt:
                return dt

    mid = shortcode_to_media_id(shortcode)
    if mid is not None:
        return media_id_to_datetime(mid)
    return None
