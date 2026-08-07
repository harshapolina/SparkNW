"""Decode Instagram shortcode / media id → post datetime (no network)."""

from __future__ import annotations

from datetime import datetime, timezone

_IG_EPOCH_MS = 1_314_220_021_721
_IG_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"


def infer_posted_at_iso(*, shortcode: str | None = None, ig_post_id: str | None = None) -> str | None:
    mid: int | None = None
    if ig_post_id and str(ig_post_id).split("_")[0].isdigit():
        mid = int(str(ig_post_id).split("_")[0])
    elif shortcode:
        code = str(shortcode).strip().rstrip("/")
        if code and all(c in _IG_ALPHABET for c in code):
            n = 0
            for ch in code:
                n = n * 64 + _IG_ALPHABET.index(ch)
            mid = n if n > 0 else None
    if not mid:
        return None
    ms = (mid >> 23) + _IG_EPOCH_MS
    if ms < _IG_EPOCH_MS or ms > 2_500_000_000_000:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).isoformat()
    except (OSError, OverflowError, ValueError):
        return None
