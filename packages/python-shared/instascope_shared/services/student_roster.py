"""Map SPARK registration-sheet columns → Profile.student dict."""

from __future__ import annotations

import re
from typing import Any

from instascope_shared.domain.instagram import extract_username

# Normalized key → possible sheet header fragments (lowercase)
# Matches the SPARK registration sheet column names exactly.
HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "timestamp": ("timestamp",),
    "full_name": ("full name", "fullname", "student name"),
    "student_id": ("student id", "studentid", "roll no", "roll"),
    "program": ("program/course", "program", "course"),
    "year_of_study": ("year of study", "year"),
    "mobile": ("mobile number", "mobile", "phone", "contact"),
    "email": ("email address", "email"),
    "university": ("university", "campus", "college"),
    "instagram_handle": (
        "instagram handle link",
        "instagram handle",
        "ig handle",
    ),
    "instagram_url": (
        "instagram_url_clean",
        "instagram url clean",
        "instagram url",
        "instagram_url",
    ),
    "instagram_username": (
        "instagram_username",
        "instagram username",
    ),
    "youtube_link": ("youtube link", "youtube url"),
    "youtube_username": ("youtube_username", "youtube username"),
    "created_content_before": (
        "have you created content before",
        "created content before",
        "have you created",
        "created content",
    ),
    "current_follower_count_raw": (
        "current follower count (insta and youtube)",
        "current follower count",
    ),
    "instagram_followers_declared": (
        "instagram_followers",
        "instagram followers",
    ),
    "youtube_subscribers_declared": (
        "youtube_subscribers",
        "youtube subscribers",
    ),
    "why_join_spark": (
        "why do you want to join spark",
        "why do you want to join",
        "why join spark",
        "why join",
    ),
    "content_interest": (
        "what type of content are you are interested in",
        "what type of content are you interested in",
        "type of content",
        "content interest",
        "interested in",
    ),
    "uid": ("uid",),
    "duplicate_flag": ("duplicate_flag", "duplicate flag", "duplicate"),
    "missing_info": ("missing_info", "missing info", "missing"),
}

# Only for Instagram/YouTube handle resolution — NOT for roster text fields.
_HANDLE_INVALID = {
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
    "youtube missing",
}

_USERNAME_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")


def _norm_header(h: str) -> str:
    # Drop punctuation noise from sheet headers like "UID (Don't Edit)"
    text = str(h or "").strip().lower().replace("_", " ")
    text = re.sub(r"[\"'`]", "", text)
    text = re.sub(r"[^\w\s/()+.-]", " ", text)
    return " ".join(text.split())


def _is_empty_cell(text: str) -> bool:
    """True only for truly empty / null-like cells (keeps Yes/No answers)."""
    t = text.strip().lower()
    return t in {"", "nan", "none", "null"}


def _is_invalid_handle(text: str) -> bool:
    t = text.strip().lower()
    if t in _HANDLE_INVALID:
        return True
    if t in {"no", "yes"}:
        return True
    if "suspended" in t or "not have" in t or "don't have" in t or "dont have" in t:
        return True
    if "no youtube" in t or "no instagram" in t or "no insta" in t:
        return True
    return False


def _first_instagram_candidate(raw: str) -> str:
    """Pick the first usable Instagram URL/handle from multi-value cells."""
    text = (raw or "").strip()
    if not text or _is_invalid_handle(text):
        return ""
    parts = re.split(r"\s+(?:AND|and|&)\s+|,\s*(?=https?://|@)|;\s*", text)
    for part in parts:
        cand = part.strip()
        if not cand or _is_invalid_handle(cand):
            continue
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
                    if alias in hk or (len(hk) >= 4 and hk in alias):
                        idx = hi
                        break
            if idx is None or idx >= len(values):
                continue
            raw = values[idx]
            text = str(raw).strip() if raw is not None else ""
            if text and not _is_empty_cell(text):
                student[field] = text
                break

    url = resolve_instagram_url(student)
    if url:
        try:
            student.setdefault("instagram_username", extract_username(url))
            student.setdefault("instagram_url", url)
        except ValueError:
            pass
    return {"student": student, "url": url or ""}


def merge_student(existing: dict | None, incoming: dict | None) -> dict:
    out = dict(existing or {})
    for k, v in (incoming or {}).items():
        if v is None or v == "":
            continue
        out[k] = v
    out.setdefault("youtube_status", "Coming soon")
    return out
