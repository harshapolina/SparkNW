"""Enqueue / status helpers for YouTube sync jobs (Celery-backed)."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Iterable

from instascope_shared.core.config import get_settings
from instascope_shared.models import (
    Job,
    JobStatus,
    JobType,
    Profile,
    YouTubeChannel,
    YouTubeSyncStatus,
)

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


def channel_already_synced(ch: Any) -> bool:
    """True when this channel has a completed successful sync we can skip."""
    if ch is None:
        return False
    last = getattr(ch, "last_synced_at", None)
    if not last:
        return False
    sync = getattr(ch, "sync_status", None)
    val = sync.value if hasattr(sync, "value") else str(sync or "")
    return val == YouTubeSyncStatus.SUCCESS.value


def _youtube_job_dispatch_row(job: Job, *, countdown: int = 0) -> dict[str, Any]:
    meta = dict(job.meta or {})
    action = str(meta.get("action") or "sync")
    return {
        "job_id": str(job.id),
        "profile_id": str(job.profile_id or ""),
        "channel_id": meta.get("channel_id"),
        "url": meta.get("channel_url"),
        "countdown": max(0, int(countdown)),
        "action": action,
        "status": job.status.value if hasattr(job.status, "value") else str(job.status),
    }


async def list_active_youtube_jobs_for_dispatch(
    *,
    reset_stale_running: bool = False,
    stale_seconds: int = 180,
) -> list[dict[str, Any]]:
    """Pending/running YouTube jobs to re-send to Celery after a restart.

    If the worker died mid-job, RUNNING rows never finish. On API startup we
    reset those to PENDING so they pick up again instead of sitting forever.
    """
    active = await Job.find(
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
    ).sort(+Job.created_at).to_list()

    now = datetime.utcnow()
    out: list[dict[str, Any]] = []
    for i, job in enumerate(active):
        status_val = job.status.value if hasattr(job.status, "value") else str(job.status)
        if status_val == JobStatus.RUNNING.value:
            started = job.started_at
            if started is not None and getattr(started, "tzinfo", None) is not None:
                started = started.replace(tzinfo=None)
            age = (now - started).total_seconds() if started else None
            stale = reset_stale_running or age is None or age > stale_seconds
            if stale:
                job.status = JobStatus.PENDING
                await job.save()
            elif not reset_stale_running:
                # Live worker still owns it — don't double-dispatch.
                continue
        out.append(_youtube_job_dispatch_row(job, countdown=i))
    return out


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


async def enqueue_connected_youtube_syncs(
    *,
    stagger_seconds: float | None = None,
    skip_successful: bool = False,
) -> dict[str, Any]:
    """Create PENDING sync_youtube jobs for connected channels.

    Skips profiles that already have a pending/running YouTube job.
    When skip_successful=True (manual Sync / resume), channels that already
    completed a successful sync are left alone so the queue continues from
    unfinished accounts. Daily morning fan-out keeps skip_successful=False.
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
    skipped_synced = 0
    for i, ch in enumerate(channels):
        pid = ch.profile_id
        if skip_successful and channel_already_synced(ch):
            skipped_synced += 1
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
                "action": "sync",
            }
        )

    summary = {
        "enqueued": len(jobs_out),
        "skipped_pending": skipped_pending,
        "skipped_synced": skipped_synced,
        "connected_total": len(channels),
        "stagger_seconds": stagger,
        "jobs": jobs_out,
    }
    logger.info("YouTube sync enqueue %s", {k: v for k, v in summary.items() if k != "jobs"})
    return summary


async def resume_unfinished_youtube_syncs(
    *,
    reset_stale_running: bool = False,
    skip_successful: bool = True,
    enqueue_unfinished: bool = True,
) -> dict[str, Any]:
    """Re-dispatch leftover jobs and optionally enqueue channels that never finished."""
    resumed_jobs = await list_active_youtube_jobs_for_dispatch(
        reset_stale_running=reset_stale_running,
    )
    if enqueue_unfinished:
        enqueued = await enqueue_connected_youtube_syncs(skip_successful=skip_successful)
    else:
        enqueued = {
            "enqueued": 0,
            "skipped_pending": 0,
            "skipped_synced": 0,
            "connected_total": 0,
            "jobs": [],
        }
    return {
        "resumed": len(resumed_jobs),
        "resumed_jobs": resumed_jobs,
        **enqueued,
    }


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

    def _youtube_job_error(job: Job, ch: YouTubeChannel | None) -> str | None:
        raw = (job.error_message or "").strip()
        if not raw:
            return (ch.last_error or None) if ch else None
        low = raw.lower()
        # Old bug: retry_failed re-ran YouTube jobs as Instagram scrapes and
        # overwrote the real YouTube error with proxy messages.
        if "instagram" in low or "http fallback enabled" in low or "login wall" in low:
            if ch and (ch.last_error or "").strip():
                return str(ch.last_error).strip()[:280]
            return "YouTube sync failed — retry Sync (ignore stale Instagram retry noise)"
        # YouTube API sometimes returns HTML-ish tokens like <code>playlistId</code>
        cleaned = re.sub(r"</?code>", "", raw)
        cleaned = re.sub(r"<[^>]+>", "", cleaned)
        return cleaned.strip()[:280] or None

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
            "error_message": _youtube_job_error(job, ch),
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

    def _job_status_for(pid: str) -> str | None:
        job = active_by_pid.get(pid)
        if not job:
            return None
        return job.status.value if hasattr(job.status, "value") else str(job.status)

    def _scrape_fields(
        *,
        ch: YouTubeChannel | None,
        youtube_ref: str | None,
        job_status: str | None,
    ) -> dict[str, Any]:
        """Human-readable scrape outcome for the admin board."""
        if job_status in {
            JobStatus.PENDING.value,
            JobStatus.RUNNING.value,
            JobStatus.RETRYING.value,
            "pending",
            "running",
            "retrying",
        }:
            return {
                "scraped": False,
                "scrape_label": "Syncing",
                "reason": "YouTube sync is in the queue or running now",
            }

        if ch and ch.connected:
            sync = (
                ch.sync_status.value
                if hasattr(ch.sync_status, "value")
                else str(ch.sync_status or "")
            )
            err = (ch.last_error or "").strip()
            if ch.last_synced_at and sync == "success":
                return {
                    "scraped": True,
                    "scrape_label": "Scraped",
                    "reason": "YouTube channel synced successfully",
                }
            if sync == "quota_exceeded":
                return {
                    "scraped": False,
                    "scrape_label": "Not scraped",
                    "reason": err or "YouTube API quota exceeded — try again later",
                }
            if sync == "failed":
                return {
                    "scraped": False,
                    "scrape_label": "Not scraped",
                    "reason": err or "Last YouTube sync failed",
                }
            if sync == "unavailable":
                return {
                    "scraped": False,
                    "scrape_label": "Not scraped",
                    "reason": err or "YouTube channel unavailable or not found",
                }
            if not ch.last_synced_at:
                return {
                    "scraped": False,
                    "scrape_label": "Not scraped",
                    "reason": "Channel connected, but no successful sync yet",
                }
            return {
                "scraped": False,
                "scrape_label": "Not scraped",
                "reason": err or f"Sync status: {sync or 'unknown'}",
            }

        if youtube_ref:
            return {
                "scraped": False,
                "scrape_label": "Not scraped",
                "reason": "YouTube link on roster — channel not connected yet",
            }

        return {
            "scraped": False,
            "scrape_label": "Not scraped",
            "reason": "No YouTube link in roster",
        }

    connected_rows = []
    for ch in sorted(
        channels,
        key=lambda c: c.last_synced_at or datetime.min,
        reverse=True,
    ):
        p = profiles.get(ch.profile_id)
        student = getattr(p, "student", None) or {}
        job_status = _job_status_for(ch.profile_id)
        scrape = _scrape_fields(ch=ch, youtube_ref=None, job_status=job_status)
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
                "job_status": job_status,
                "last_error": ch.last_error,
                "last_synced_at": ch.last_synced_at.isoformat() + "Z"
                if ch.last_synced_at
                else None,
                "subscriber_count": ch.subscriber_count,
                "hidden_subscriber_count": bool(ch.hidden_subscriber_count),
                "view_count": int(ch.view_count or 0),
                "video_count": int(ch.video_count or 0),
                "connected": True,
                **scrape,
            }
        )

    # Full roster board: every profile, with why scraped / not scraped
    all_profiles = await Profile.find_all().limit(5000).to_list()
    for p in all_profiles:
        profiles[str(p.id)] = p

    board: list[dict[str, Any]] = []
    seen_pids: set[str] = set()
    for p in sorted(
        all_profiles,
        key=lambda x: (
            0 if channels_by_profile.get(str(x.id)) else 1,
            (getattr(x, "username", None) or "").lower(),
        ),
    ):
        pid = str(p.id)
        seen_pids.add(pid)
        student = dict(getattr(p, "student", None) or {})
        ref = youtube_ref_from_student(student)
        ch = channels_by_profile.get(pid)
        job_status = _job_status_for(pid)
        scrape = _scrape_fields(ch=ch, youtube_ref=ref, job_status=job_status)
        board.append(
            {
                "profile_id": pid,
                "username": getattr(p, "username", None) or "—",
                "full_name": getattr(p, "full_name", None) or student.get("full_name"),
                "student_id": student.get("student_id"),
                "university": student.get("university"),
                "channel_id": ch.channel_id if ch else None,
                "channel_name": ch.channel_name if ch else None,
                "handle": ch.handle if ch else None,
                "thumbnail_url": ch.thumbnail_url if ch else None,
                "sync_status": (
                    (
                        ch.sync_status.value
                        if hasattr(ch.sync_status, "value")
                        else str(ch.sync_status)
                    )
                    if ch
                    else ("not_connected" if ref else "no_youtube")
                ),
                "job_status": job_status,
                "last_error": ch.last_error if ch else None,
                "last_synced_at": ch.last_synced_at.isoformat() + "Z"
                if ch and ch.last_synced_at
                else None,
                "subscriber_count": ch.subscriber_count if ch else None,
                "hidden_subscriber_count": bool(ch.hidden_subscriber_count) if ch else False,
                "view_count": int(ch.view_count or 0) if ch else 0,
                "video_count": int(ch.video_count or 0) if ch else 0,
                "connected": bool(ch and ch.connected),
                "youtube_ref": ref,
                **scrape,
            }
        )

    # Orphan channels without a profile doc (rare)
    for ch in channels:
        if ch.profile_id in seen_pids:
            continue
        job_status = _job_status_for(ch.profile_id)
        scrape = _scrape_fields(ch=ch, youtube_ref=None, job_status=job_status)
        board.append(
            {
                "profile_id": ch.profile_id,
                "username": "—",
                "full_name": None,
                "student_id": None,
                "university": None,
                "channel_id": ch.channel_id,
                "channel_name": ch.channel_name,
                "handle": ch.handle,
                "thumbnail_url": ch.thumbnail_url,
                "sync_status": ch.sync_status.value
                if hasattr(ch.sync_status, "value")
                else str(ch.sync_status),
                "job_status": job_status,
                "last_error": ch.last_error,
                "last_synced_at": ch.last_synced_at.isoformat() + "Z"
                if ch.last_synced_at
                else None,
                "subscriber_count": ch.subscriber_count,
                "hidden_subscriber_count": bool(ch.hidden_subscriber_count),
                "view_count": int(ch.view_count or 0),
                "video_count": int(ch.video_count or 0),
                "connected": True,
                "youtube_ref": None,
                **scrape,
            }
        )

    scraped_total = sum(1 for r in board if r.get("scraped"))
    not_scraped_total = len(board) - scraped_total

    return {
        "running": running,
        "queue": queue,
        "active_count": len(queue),
        "history": history,
        "connected": connected_rows,
        "connected_total": len(connected_rows),
        "board": board,
        "board_total": len(board),
        "scraped_total": scraped_total,
        "not_scraped_total": not_scraped_total,
    }
