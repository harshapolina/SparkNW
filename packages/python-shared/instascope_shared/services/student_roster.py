"""Map SPARK registration-sheet columns → Profile.student dict."""

from __future__ import annotations

import re
from typing import Any

from instascope_shared.domain.instagram import extract_username

# Normalized key → possible sheet header fragments (lowercase)
HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "timestamp": ("timestamp",),
    "full_name": ("full name", "fullname", "student name"),
    "student_id": ("student id", "studentid", "roll"),
    "program": ("program", "course", "program/course"),
    "year_of_study": ("year of study", "year"),
    "mobile": ("mobile", "phone", "contact"),
    "email": ("email",),
    "university": ("university", "campus", "college"),
    "instagram_handle": ("instagram handle", "instagram handle link", "ig handle"),
    "instagram_url": ("instagram_url_clean", "instagram url", "instagram_url"),
    "instagram_username": ("instagram_username", "instagram username"),
    "youtube_link": ("youtube link", "youtube url"),
    "youtube_username": ("youtube_username", "youtube username"),
    "created_content_before": ("created content", "have you created"),
    "current_follower_count_raw": ("current follower count",),
    "instagram_followers_declared": ("instagram_followers", "instagram followers"),
    "youtube_subscribers_declared": ("youtube_subscribers", "youtube subscribers"),
    "why_join_spark": ("why do you want to join", "why join"),
    "content_interest": ("type of content", "content interest", "interested in"),
    "uid": ("uid",),
    "duplicate_flag": ("duplicate",),
    "missing_info": ("missing",),
}

_INVALID_MARKERS = {
    "",
    "nan",
    "none",
    "null",
    "-",
    ".",
    "./",
    "na",
    "n/a",
    "nil",
    "no",
    "yes",
    "invites",
    "don't",
    "dont",
    "not yet",
    "not started",
    "not created",
    "no account",
    "no insta",
    "my id was suspended",
    "not yet started",
    "yet to create",
    "will start",
}

_USERNAME_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")


def _norm_header(h: str) -> str:
    return " ".join(str(h or "").strip().lower().replace("_", " ").split())


def _is_blank(text: str) -> bool:
    t = text.strip().lower()
    if t in _INVALID_MARKERS:
        return True
    if "suspended" in t or "not have" in t or "don't have" in t or "dont have" in t:
        return True
    if "no youtube" in t or "no instagram" in t or "no insta" in t:
        return True
    return False


def _first_instagram_candidate(raw: str) -> str:
    """Pick the first usable Instagram URL/handle from multi-value cells."""
    text = (raw or "").strip()
    if not text or _is_blank(text):
        return ""
    # Split common multi-handle separators
    parts = re.split(r"\s+(?:AND|and|&)\s+|,\s*(?=https?://|@)|;\s*", text)
    for part in parts:
        cand = part.strip()
        if not cand or _is_blank(cand):
            continue
        # Prefer full Instagram URLs
        if "instagram.com" in cand.lower():
            m = re.search(r"https?://(?:www\.)?instagram\.com/[A-Za-z0-9._]+/?", cand, re.I)
            if m:
                return m.group(0).rstrip("/")
            return cand.split()[0]
        if cand.startswith("@"):
            return cand
        if _USERNAME_RE.match(cand) and " " not in cand:
            return cand
    return ""


def resolve_instagram_url(student: dict[str, Any]) -> str | None:
    """Return a scrapeable Instagram URL/username, or None if missing/invalid."""
    ordered = [
        student.get("instagram_username"),
        student.get("instagram_url"),
        student.get("instagram_handle"),
    ]
    for raw in ordered:
        cand = _first_instagram_candidate(str(raw or ""))
        if not cand:
            continue
        try:
            username = extract_username(cand)
        except ValueError:
            continue
        if username.lower() in {"invites", "reel", "reels", "p", "explore", "stories"}:
            continue
        return f"https://www.instagram.com/{username}"
    return None


def map_sheet_row(headers: list[str], values: list[Any]) -> dict[str, Any]:
    """Build student dict + pick best Instagram URL/username from a sheet row."""
    header_map = {_norm_header(h): i for i, h in enumerate(headers)}
    student: dict[str, Any] = {"youtube_status": "Coming soon"}

    for field, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            idx = header_map.get(_norm_header(alias))
            if idx is None:
                for hk, hi in header_map.items():
                    if alias in hk or hk in alias:
                        idx = hi
                        break
            if idx is None or idx >= len(values):
                continue
            raw = values[idx]
            text = str(raw).strip() if raw is not None else ""
            if text and not _is_blank(text):
                student[field] = text
                break

    url = resolve_instagram_url(student)
    return {"student": student, "url": url or ""}


def merge_student(existing: dict | None, incoming: dict | None) -> dict:
    out = dict(existing or {})
    for k, v in (incoming or {}).items():
        if v is None or v == "":
            continue
        out[k] = v
    out.setdefault("youtube_status", "Coming soon")
    return out
