"""Enrich top50 JSON with student_id + IG/YT links from MongoDB."""
from __future__ import annotations

import json
import os
from pathlib import Path

from pymongo import MongoClient

root = Path(__file__).resolve().parents[1]
for line in (root / ".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    os.environ.setdefault(k.strip(), v.strip())

data = json.loads((root / "scripts" / "top50_leaderboard.json").read_text(encoding="utf-8"))
usernames = [r["username"] for r in data["top50"]]

client = MongoClient(os.environ["MONGODB_URI"], serverSelectionTimeoutMS=20000)
db = client[os.environ.get("MONGODB_DB", "instascope")]
profiles = {p["username"]: p for p in db.profiles.find({"username": {"$in": usernames}})}
pids = [str(p["_id"]) for p in profiles.values()]
channels = {c["profile_id"]: c for c in db.youtube_channels.find({"profile_id": {"$in": pids}})}


def ig_url(profile: dict, username: str, student: dict) -> str:
    raw = student.get("instagram_url") or student.get("instagram_handle") or profile.get("profile_url")
    if isinstance(raw, str) and raw.strip():
        raw = raw.strip()
        if "instagram.com" in raw.lower() or raw.startswith("http"):
            return raw.split("?")[0].rstrip("/") + "/"
        handle = raw.lstrip("@").strip("/")
        return f"https://www.instagram.com/{handle}/"
    return f"https://www.instagram.com/{username}/"


def yt_url(profile: dict, student: dict, channel: dict) -> str | None:
    candidates: list[str] = []
    if channel.get("channel_url"):
        candidates.append(str(channel["channel_url"]).strip())
    handle = channel.get("handle")
    if handle:
        h = str(handle).strip()
        if not h.startswith("@"):
            h = "@" + h.lstrip("@")
        candidates.append(f"https://www.youtube.com/{h}")
    cid = profile.get("youtube_channel_id") or channel.get("channel_id")
    if cid and str(cid).startswith("UC"):
        candidates.append(f"https://www.youtube.com/channel/{cid}")
    if student.get("youtube_link"):
        candidates.append(str(student["youtube_link"]).strip())

    junk = {
        "",
        "-",
        "--",
        "n/a",
        "na",
        "none",
        "null",
        "not there for now",
        "i am not youtube account",
        "i don't have an acc",
        "not have",
    }
    for raw in candidates:
        s = raw.strip().split("?")[0].strip()
        low = s.lower()
        if low in junk or "instagram.com" in low:
            continue
        if "youtube.com" in low or "youtu.be" in low:
            if not s.startswith("http"):
                s = "https://" + s.lstrip("/")
            return s
        # bare @handle from roster
        if s.startswith("@") and " " not in s and len(s) > 2:
            return f"https://www.youtube.com/{s}"
    return None


enriched = []
for r in data["top50"]:
    p = profiles.get(r["username"]) or {}
    st = p.get("student") if isinstance(p.get("student"), dict) else {}
    pid = str(p.get("_id", ""))
    ch = channels.get(pid) or {}
    enriched.append(
        {
            **r,
            "student_id": st.get("student_id") or None,
            "instagram_url": ig_url(p, r["username"], st),
            "youtube_url": yt_url(p, st, ch),
            "youtube_handle": ch.get("handle") or st.get("youtube_username"),
        }
    )

out = {**data, "top50": enriched}
(root / "scripts" / "top50_leaderboard.json").write_text(
    json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
)
print("ok", len(enriched))
print("sample", enriched[0]["student_id"], enriched[0]["instagram_url"], enriched[0]["youtube_url"])
print("missing_id", sum(1 for e in enriched if not e.get("student_id")))
print("missing_yt", sum(1 for e in enriched if not e.get("youtube_url")))
