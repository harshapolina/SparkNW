"""Top 50 overall SPARK leaderboard from MongoDB Atlas (pymongo, no Beanie)."""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from pymongo import MongoClient

root = Path(__file__).resolve().parents[1]
env_path = root / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, str(root / "packages" / "python-shared"))

from instascope_shared.cohort import clamp_scoring_window
from instascope_shared.services.spark_points import (
    compute_points_breakdown,
    growth_points_for_window,
)


def _ns(**kwargs):
    return SimpleNamespace(**kwargs)


def main() -> None:
    uri = os.environ["MONGODB_URI"]
    db_name = os.environ.get("MONGODB_DB", "instascope")
    client = MongoClient(uri, serverSelectionTimeoutMS=20000)
    db = client[db_name]

    window_start, window_end = clamp_scoring_window(None, None)
    start_ymd = window_start.strftime("%Y-%m-%d")
    end_ymd = window_end.strftime("%Y-%m-%d")

    profiles = list(db.profiles.find({}))
    profile_ids = [str(p["_id"]) for p in profiles]

    posts_by: dict[str, list] = defaultdict(list)
    for doc in db.posts.find({"profile_id": {"$in": profile_ids}}):
        posts_by[doc["profile_id"]].append(
            _ns(
                media_type=doc.get("media_type") or "unknown",
                views=int(doc.get("views") or 0),
                posted_at=doc.get("posted_at"),
                caption=doc.get("caption"),
                shortcode=doc.get("shortcode") or doc.get("ig_post_id") or str(doc.get("_id")),
                ig_post_id=doc.get("ig_post_id"),
                likes=int(doc.get("likes") or 0),
                comments=int(doc.get("comments") or 0),
            )
        )

    videos_by: dict[str, list] = defaultdict(list)
    for doc in db.youtube_videos.find({"profile_id": {"$in": profile_ids}}):
        videos_by[doc["profile_id"]].append(
            _ns(
                view_count=int(doc.get("view_count") or 0),
                published_at=doc.get("published_at"),
                is_short=bool(doc.get("is_short")),
                duration_seconds=doc.get("duration_seconds"),
                video_id=doc.get("video_id") or str(doc.get("_id")),
                like_count=int(doc.get("like_count") or 0) if doc.get("like_count") is not None else 0,
                comment_count=int(doc.get("comment_count") or 0)
                if doc.get("comment_count") is not None
                else 0,
            )
        )

    # IG follower snapshots
    ig_start: dict[str, int] = {}
    ig_start_d: dict[str, str] = {}
    ig_end: dict[str, int] = {}
    ig_end_d: dict[str, str] = {}
    earliest_in_window: dict[str, tuple[str, int]] = {}
    for s in db.profile_snapshots.find({"profile_id": {"$in": profile_ids}}):
        pid = s["profile_id"]
        d = s.get("snapshot_date") or ""
        fol = int(s.get("followers") or 0)
        if d <= start_ymd:
            if pid not in ig_start or d > ig_start_d.get(pid, ""):
                ig_start[pid] = fol
                ig_start_d[pid] = d
        if d <= end_ymd:
            if pid not in ig_end or d > ig_end_d.get(pid, ""):
                ig_end[pid] = fol
                ig_end_d[pid] = d
        if start_ymd <= d <= end_ymd:
            prev = earliest_in_window.get(pid)
            if prev is None or d < prev[0]:
                earliest_in_window[pid] = (d, fol)

    for pid, (d, fol) in earliest_in_window.items():
        if pid not in ig_start:
            ig_start[pid] = fol

    # YT subscriber snapshots + channels
    yt_start: dict[str, int] = {}
    yt_start_d: dict[str, str] = {}
    yt_end: dict[str, int] = {}
    yt_end_d: dict[str, str] = {}
    yt_earliest: dict[str, tuple[str, int]] = {}
    for s in db.youtube_snapshots.find({"profile_id": {"$in": profile_ids}}):
        pid = s["profile_id"]
        d = s.get("snapshot_date") or ""
        if s.get("subscribers") is None:
            continue
        subs = int(s["subscribers"])
        if d <= start_ymd:
            if pid not in yt_start or d > yt_start_d.get(pid, ""):
                yt_start[pid] = subs
                yt_start_d[pid] = d
        if d <= end_ymd:
            if pid not in yt_end or d > yt_end_d.get(pid, ""):
                yt_end[pid] = subs
                yt_end_d[pid] = d
        if start_ymd <= d <= end_ymd:
            prev = yt_earliest.get(pid)
            if prev is None or d < prev[0]:
                yt_earliest[pid] = (d, subs)
    for pid, (d, subs) in yt_earliest.items():
        if pid not in yt_start:
            yt_start[pid] = subs

    channels = {c["profile_id"]: c for c in db.youtube_channels.find({"profile_id": {"$in": profile_ids}})}
    for pid, ch in channels.items():
        if ch.get("subscriber_count") is None:
            continue
        subs = int(ch["subscriber_count"])
        if pid not in yt_end:
            yt_end[pid] = subs
        if pid not in yt_start:
            yt_start[pid] = subs

    include_yt = os.environ.get("YOUTUBE_SCORING_ENABLED", "1").strip() not in {"0", "false", "False"}

    rows = []
    for p in profiles:
        pid = str(p["_id"])
        end_ig = int(ig_end.get(pid, p.get("followers") or 0) or 0)
        start_ig = int(ig_start.get(pid, 0) or 0)
        end_yt = int(yt_end.get(pid, 0) or 0) if include_yt else 0
        start_yt = int(yt_start.get(pid, 0) or 0) if include_yt else 0
        growth = growth_points_for_window(
            end_ig=end_ig, end_yt=end_yt, start_ig=start_ig, start_yt=start_yt
        )
        scored = compute_points_breakdown(
            posts=posts_by.get(pid, []),
            videos=videos_by.get(pid, []) if include_yt else [],
            followers=end_ig,
            yt_subscribers=end_yt,
            start_followers=start_ig,
            start_yt_subscribers=start_yt,
            as_of=window_end,
            from_date=window_start,
            insights=p.get("insights") or {},
            growth_pts_override=growth,
            include_youtube=include_yt,
        )
        student = p.get("student") or {}
        campus = (
            (student.get("university") if isinstance(student, dict) else None)
            or (student.get("campus") if isinstance(student, dict) else None)
            or ((p.get("insights") or {}).get("campus") if isinstance(p.get("insights"), dict) else None)
            or "—"
        )
        rows.append(
            {
                "username": p.get("username"),
                "name": p.get("full_name") or p.get("username"),
                "campus": campus,
                "points": scored["points"],
                "consistency": scored["consistency"],
                "performance": scored["performance"],
                "growth": scored["growth"],
                "collaborations": scored["collaborations"],
                "revenue": scored["revenue"],
                "recognition": scored["recognition"],
                "participation": scored["participation"],
                "monthly_bonuses": scored["monthly_bonuses"],
                "bonus": scored["bonus"],
                "followers": end_ig,
                "youtube_subscribers": end_yt or None,
                "combined_audience": end_ig + end_yt,
                "tier": (
                    "GOLD"
                    if scored["points"] >= 2500
                    else "SILVER"
                    if scored["points"] >= 1500
                    else "BRONZE"
                ),
            }
        )

    rows.sort(key=lambda r: (-r["points"], -r["followers"]))
    for i, r in enumerate(rows[:50], 1):
        r["rank"] = i

    out = {
        "source": "MongoDB Atlas instascope",
        "sort": "overall (SPARK points)",
        "window_from": start_ymd,
        "window_to": end_ymd,
        "total_creators": len(rows),
        "youtube_scoring": include_yt,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "top50": rows[:50],
    }
    print(json.dumps(out, indent=2, default=str))
    client.close()


if __name__ == "__main__":
    main()
