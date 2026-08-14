"""Enqueue / status helpers for YouTube sync jobs (Celery-backed)."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Iterable

from instascope_shared.core.config import get_settings
from instascope_shared.models import Job, JobStatus, JobType, Profile, YouTubeChannel

logger = logging.getLogger("instascope.youtube.jobs")

_MISSING_YT_RE = re.compile(
    r"^\s*(n/?a|na|none|null|-|—|no youtube|youtube missing|coming soon)\s*$",
    re.IGNORECASE,
)


def youtube_ref_from_student(student: dict[str, Any] | None) -> str | None:
    """Pick a connectable YouTube URL/@handle from roster student fields."""
    if not isinstance(student, dict):
        return None
    for key in ("youtube_link", "youtube_url", "youtube_username", "youtube"):
        raw = str(student.get(key) or "").strip()
        if not raw or _MISSING_YT_RE.match(raw):
            continue
        # Bare handle → @handle
        if (
            "youtube.com" not in raw.lower()
            and "youtu.be" not in raw.lower()
            and not raw.startswith("UC")
            and " " not in raw
        ):
            return raw if raw.startswith("@") else f"@{raw.lstrip('@')}"
        return raw
    return None


async def enqueue_youtube_connects(
    items: Iterable[tuple[str, str, str]],
    *,
    stagger_seconds: float | None = None,
    source: str = "bulk_import",
) -> dict[str, Any]:
    """Enqueue connect+sync jobs: (profile_id, user_id, url_or_handle).

    Skips profiles that already have a pending/running YouTube job.
    Returns job payloads for Celery dispatch.
    """
    settings = get_settings()
    stagger = (
        float(stagger_seconds)
        if stagger_seconds is not None
        else max(0.0, float(settings.daily_youtube_sync_stagger_seconds or 0))
    )
    jobs_out: list[dict[str, Any]] = []
    skipped_pending = 0
    skipped_empty = 0
    for i, (profile_id, user_id, url) in enumerate(items):
        pid = str(profile_id or "").strip()
        ref = str(url or "").strip()
        if not pid or not ref:
            skipped_empty += 1
            continue
        existing = await Job.find_one(
            Job.profile_id == pid,
            Job.job_type == JobType.SYNC_YOUTUBE,
            {
                "status": {
                    "$in": [
                        JobStatus.PENDING,
                        JobStatus.RUNNING,
                        JobStatus.RETRYING,
                    ]
                }
            },
        )
        if existing is not None:
            skipped_pending += 1
            continue

        job = Job(
            user_id=str(user_id),
            profile_id=pid,
            job_type=JobType.SYNC_YOUTUBE,
            status=JobStatus.PENDING,
            priority=6,
            scheduled_at=datetime.utcnow(),
            meta={"channel_url": ref[:300], "source": source, "action": "connect"},
        )
        await job.insert()
        countdown = int(i * stagger) if stagger > 0 else 0
        jobs_out.append(
            {
                "job_id": str(job.id),
                "profile_id": pid,
                "url": ref,
                "countdown": countdown,
                "action": "connect",
            }
        )

    summary = {
        "enqueued": len(jobs_out),
        "skipped_pending": skipped_pending,
        "skipped_empty": skipped_empty,
        "stagger_seconds": stagger,
        "jobs": jobs_out,
    }
    logger.info(
        "YouTube connect enqueue %s",
        {k: v for k, v in summary.items() if k != "jobs"},
    )
    return summary


async def enqueue_connected_youtube_syncs(*, stagger_seconds: float | None = None) -> dict[str, Any]:
    """Create PENDING sync_youtube jobs for every connected channel.

    Skips profiles that already have a pending/running YouTube job.
    Returns job payloads for the API to dispatch via Celery (or empty if none).
    """
    settings = get_settings()
    stagger = (
        float(stagger_seconds)
        if stagger_seconds is not None
        else max(0.0, float(settings.daily_youtube_sync_stagger_seconds or 0))
    )
    channels = await YouTubeChannel.find(YouTubeChannel.connected == True).to_list()  # noqa: E712

    jobs_out: list[dict[str, Any]] = []
    skipped_pending = 0
    for i, ch in enumerate(channels):
        pid = ch.profile_id
        existing = await Job.find_one(
            Job.profile_id == pid,
            Job.job_type == JobType.SYNC_YOUTUBE,
            {
                "status": {
                    "$in": [
                        JobStatus.PENDING,
                        JobStatus.RUNNING,
                        JobStatus.RETRYING,
                    ]
                }
            },
        )
        if existing is not None:
            skipped_pending += 1
            continue

        job = Job(
            user_id=ch.user_id,
            profile_id=pid,
            job_type=JobType.SYNC_YOUTUBE,
            status=JobStatus.PENDING,
            priority=5,
            scheduled_at=datetime.utcnow(),
            meta={"channel_id": ch.channel_id, "source": "fanout"},
        )
        await job.insert()
        countdown = int(i * stagger) if stagger > 0 else 0
        jobs_out.append(
            {
                "job_id": str(job.id),
                "profile_id": pid,
                "channel_id": ch.channel_id,
                "countdown": countdown,
            }
        )

    summary = {
        "enqueued": len(jobs_out),
        "skipped_pending": skipped_pending,
        "connected_total": len(channels),
        "stagger_seconds": stagger,
        "jobs": jobs_out,
    }
    logger.info("YouTube sync enqueue %s", {k: v for k, v in summary.items() if k != "jobs"})
    return summary


async def get_youtube_sync_status(*, recent_limit: int = 40) -> dict[str, Any]:
    """Queue + recent history for admin Scraping page."""
    active_jobs = (
        await Job.find(
            Job.job_type == JobType.SYNC_YOUTUBE,
            {
                "status": {
                    "$in": [
                        JobStatus.PENDING,
                        JobStatus.RUNNING,
                        JobStatus.RETRYING,
                    ]
                }
            },
        )
        .sort(-Job.created_at)
        .to_list()
    )

    recent_jobs = (
        await Job.find(
            Job.job_type == JobType.SYNC_YOUTUBE,
            {
                "status": {
                    "$in": [
                        JobStatus.SUCCESS,
                        JobStatus.FAILED,
                    ]
                }
            },
        )
        .sort(-Job.finished_at)
        .limit(max(1, min(100, recent_limit)))
        .to_list()
    )

    profile_ids = {
        str(j.profile_id)
        for j in active_jobs + recent_jobs
        if j.profile_id
    }
    channels = await YouTubeChannel.find(YouTubeChannel.connected == True).to_list()  # noqa: E712
    for ch in channels:
        profile_ids.add(ch.profile_id)

    profiles: dict[str, Profile] = {}
    for pid in profile_ids:
        if not pid:
            continue
        p = await Profile.get(pid)
        if p:
            profiles[pid] = p

    channels_by_profile = {ch.profile_id: ch for ch in channels}

    def _job_row(job: Job) -> dict[str, Any]:
        pid = str(job.profile_id or "")
        p = profiles.get(pid)
        ch = channels_by_profile.get(pid)
        student = getattr(p, "student", None) or {}
        return {
            "job_id": str(job.id),
            "profile_id": pid,
            "username": getattr(p, "username", None) or "—",
            "full_name": getattr(p, "full_name", None)
            or (student.get("full_name") if isinstance(student, dict) else None),
            "channel_id": (job.meta or {}).get("channel_id")
            or (ch.channel_id if ch else None),
            "channel_name": ch.channel_name if ch else None,
            "status": job.status.value if hasattr(job.status, "value") else str(job.status),
            "error_message": job.error_message,
            "created_at": job.created_at.isoformat() + "Z" if job.created_at else None,
            "started_at": job.started_at.isoformat() + "Z" if job.started_at else None,
            "finished_at": job.finished_at.isoformat() + "Z" if job.finished_at else None,
            "meta": dict(job.meta or {}),
        }

    queue = [_job_row(j) for j in active_jobs]
    # Running first
    queue.sort(
        key=lambda r: (
            0 if r["status"] == JobStatus.RUNNING.value else 1,
            r.get("created_at") or "",
        )
    )
    running = next((r for r in queue if r["status"] == JobStatus.RUNNING.value), None)
    if running is None and queue:
        running = queue[0]

    history = [_job_row(j) for j in recent_jobs]

    active_by_pid = {
        str(j.profile_id): j for j in active_jobs if j.profile_id
    }

    connected_rows = []
    for ch in sorted(
        channels,
        key=lambda c: c.last_synced_at or datetime.min,
        reverse=True,
    ):
        p = profiles.get(ch.profile_id)
        student = getattr(p, "student", None) or {}
        connected_rows.append(
            {
                "profile_id": ch.profile_id,
                "username": getattr(p, "username", None) or "—",
                "full_name": getattr(p, "full_name", None)
                or (student.get("full_name") if isinstance(student, dict) else None),
                "student_id": student.get("student_id") if isinstance(student, dict) else None,
                "university": student.get("university") if isinstance(student, dict) else None,
                "channel_id": ch.channel_id,
                "channel_name": ch.channel_name,
                "handle": ch.handle,
                "thumbnail_url": ch.thumbnail_url,
                "sync_status": ch.sync_status.value
                if hasattr(ch.sync_status, "value")
                else str(ch.sync_status),
                "job_status": (
                    active_by_pid[ch.profile_id].status.value
                    if ch.profile_id in active_by_pid
                    and hasattr(active_by_pid[ch.profile_id].status, "value")
                    else (
                        str(active_by_pid[ch.profile_id].status)
                        if ch.profile_id in active_by_pid
                        else None
                    )
                ),
                "last_error": ch.last_error,
                "last_synced_at": ch.last_synced_at.isoformat() + "Z"
                if ch.last_synced_at
                else None,
                "subscriber_count": ch.subscriber_count,
                "hidden_subscriber_count": bool(ch.hidden_subscriber_count),
                "view_count": int(ch.view_count or 0),
                "video_count": int(ch.video_count or 0),
                "connected": True,
            }
        )

    # Roster rows with a YouTube link that are not connected yet
    pending_connect: list[dict[str, Any]] = []
    candidates = await Profile.find({"youtube_connected": {"$ne": True}}).limit(2000).to_list()
    for p in candidates:
        student = dict(getattr(p, "student", None) or {})
        ref = youtube_ref_from_student(student)
        if not ref:
            continue
        pid = str(p.id)
        pending_connect.append(
            {
                "profile_id": pid,
                "username": getattr(p, "username", None) or "—",
                "full_name": getattr(p, "full_name", None) or student.get("full_name"),
                "student_id": student.get("student_id"),
                "university": student.get("university"),
                "channel_id": None,
                "channel_name": None,
                "handle": None,
                "thumbnail_url": None,
                "sync_status": "not_connected",
                "job_status": (
                    active_by_pid[pid].status.value
                    if pid in active_by_pid and hasattr(active_by_pid[pid].status, "value")
                    else (str(active_by_pid[pid].status) if pid in active_by_pid else None)
                ),
                "last_error": None,
                "last_synced_at": None,
                "subscriber_count": None,
                "hidden_subscriber_count": False,
                "view_count": 0,
                "video_count": 0,
                "connected": False,
                "youtube_ref": ref,
            }
        )

    board = connected_rows + pending_connect

    return {
        "running": running,
        "queue": queue,
        "active_count": len(queue),
        "history": history,
        "connected": connected_rows,
        "connected_total": len(connected_rows),
        "board": board,
        "board_total": len(board),
    }
