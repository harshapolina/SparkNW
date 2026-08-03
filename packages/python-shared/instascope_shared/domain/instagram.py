"""Domain helpers — Instagram URL parsing, metrics math."""

from __future__ import annotations

import re
from urllib.parse import urlparse


_USERNAME_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")


def extract_username(url_or_username: str) -> str:
    raw = url_or_username.strip()
    if raw.startswith("@"):
        raw = raw[1:]

    if _USERNAME_RE.match(raw) and "://" not in raw and "/" not in raw:
        return raw.lower()

    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = (parsed.netloc or "").lower().replace("www.", "")
    if host not in {"instagram.com", "instagr.am"}:
        # Allow bare path-style paste mistakes like instagram.com/user
        if "instagram.com" not in host and "instagram.com" not in raw.lower():
            raise ValueError("URL must be an Instagram profile link or @username")

    parts = [p for p in parsed.path.split("/") if p]
    if not parts:
        raise ValueError("Could not find username in URL")

    username = parts[0].lstrip("@")
    if username.lower() in {"p", "reel", "reels", "stories", "explore", "tv"}:
        raise ValueError("That looks like a post/reel URL — paste a profile URL instead")

    if not _USERNAME_RE.match(username):
        raise ValueError("Invalid Instagram username")

    return username.lower()


def profile_url_for(username: str) -> str:
    return f"https://instagram.com/{username}"


def engagement_rate(*, avg_likes: float, avg_comments: float, followers: int) -> float:
    if followers <= 0:
        return 0.0
    return round(((avg_likes + avg_comments) / followers) * 100, 4)


def growth_pct(current: int, previous: int) -> float:
    if previous <= 0:
        return 0.0 if current == 0 else 100.0
    return round(((current - previous) / previous) * 100, 4)


def mean(values: list[float | int]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)
