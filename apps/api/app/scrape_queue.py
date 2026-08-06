"""Sequential in-process scrape queue for bulk import/refresh.

Add/Refresh enqueue here and return immediately. This queue runs one scrape at
a time with a delay between jobs and keeps a strong reference to the worker
task for the life of the API process.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import traceback
from datetime import datetime
from typing import Iterable

from instascope_shared.models import Profile
from instascope_shared.services.inline_scrape import scrape_profile_inline

log = logging.getLogger("instascope.api.scrape_queue")

_queue: asyncio.Queue[str] | None = None
_worker: asyncio.Task | None = None
_pending: set[str] = set()
_lock = asyncio.Lock()
_running_id: str | None = None
_running_started: float | None = None


def _delay_seconds() -> float:
    raw = (os.getenv("SCRAPE_BULK_DELAY_SECONDS") or "").strip()
    if raw:
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass
    # Space bulk jobs so Instagram/proxy rate-limits don't kill profile #2+.
    # Single Add/Refresh still uses the same queue but usually only one id.
    try:
        return max(15.0, float(os.getenv("SCRAPE_DELAY_SECONDS") or "15"))
    except ValueError:
        return 15.0


def _stale_seconds() -> float:
    raw = (os.getenv("SCRAPE_STALE_SECONDS") or "600").strip()
    try:
        return max(120.0, float(raw))
    except ValueError:
        return 600.0


def _get_queue() -> asyncio.Queue[str]:
    global _queue
    if _queue is None:
        _queue = asyncio.Queue()
    return _queue


async def _mark_profile_interrupted(profile_id: str, reason: str) -> None:
    try:
        profile = await Profile.get(profile_id)
        if not profile:
            return
        prog = dict(getattr(profile, "scrape_progress", None) or {})
        if not prog.get("active"):
            return
        profile.scrape_progress = {
            **prog,
            "active": False,
            "phase": "interrupted",
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }
        if not profile.last_error:
            profile.last_error = reason
        profile.updated_at = datetime.utcnow()
        await profile.save()
    except Exception:
        log.exception("failed to mark interrupted profile_id=%s", profile_id)


async def clear_stale_scrape_progress() -> int:
    """Clear orphaned active scrape_progress left by API restarts / hung jobs."""
    cleared = 0
    try:
        profiles = await Profile.find({"scrape_progress.active": True}).to_list()
    except Exception:
        log.exception("clear_stale_scrape_progress query failed")
        return 0
    now = time.time()
    for profile in profiles:
        prog = dict(getattr(profile, "scrape_progress", None) or {})
        updated_raw = prog.get("updated_at") or ""
        stale = True
        if isinstance(updated_raw, str) and updated_raw:
            try:
                ts = updated_raw.replace("Z", "+00:00")
                age = now - datetime.fromisoformat(ts).timestamp()
                stale = age >= _stale_seconds()
            except Exception:
                stale = True
        if not stale:
            continue
        profile.scrape_progress = {
            **prog,
            "active": False,
            "phase": "interrupted",
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }
        if not profile.last_error:
            profile.last_error = "Previous scrape was interrupted — click Refresh to retry."
        profile.updated_at = datetime.utcnow()
        await profile.save()
        cleared += 1
        _pending.discard(str(profile.id))
    if cleared:
        log.warning("cleared %s stale scrape_progress marker(s)", cleared)
    return cleared


async def resume_incomplete_scrapes() -> int:
    """Re-enqueue profiles that were queued/running when the API process restarted.

    The scrape queue is in-memory — bulk import of 2+ profiles loses remaining jobs
    if the API restarts mid-run. Persist intent via scrape_progress, then recover here.
    """
    try:
        profiles = await Profile.find(
            {
                "$or": [
                    {"scrape_progress.active": True},
                    {
                        "scrape_progress.phase": {
                            "$in": [
                                "queued",
                                "starting",
                                "scraping",
                                "http_profile",
                                "username_feed",
                                "browser",
                                "saving",
                                "http_rescue",
                            ]
                        }
                    },
                ]
            }
        ).to_list()
    except Exception:
        log.exception("resume_incomplete_scrapes query failed")
        return 0

    now = time.time()
    to_resume: list[str] = []
    for profile in profiles:
        prog = dict(getattr(profile, "scrape_progress", None) or {})
        updated_raw = prog.get("updated_at") or ""
        age_ok = True
        if isinstance(updated_raw, str) and updated_raw:
            try:
                ts = updated_raw.replace("Z", "+00:00")
                age = now - datetime.fromisoformat(ts).timestamp()
                # Skip truly dead markers — clear_stale handles those.
                age_ok = age < _stale_seconds()
            except Exception:
                age_ok = True
        if not age_ok:
            continue
        # Still looks like a live/queued scrape — put it back on the queue.
        if not prog.get("active"):
            profile.scrape_progress = {
                **prog,
                "active": True,
                "phase": "queued",
                "updated_at": datetime.utcnow().isoformat() + "Z",
            }
            profile.updated_at = datetime.utcnow()
            await profile.save()
        to_resume.append(str(profile.id))

    if not to_resume:
        return 0
    queued = await enqueue_profile_ids(to_resume, force=True)
    if queued:
        log.warning("resumed %s incomplete scrape(s) after API restart", queued)
    return queued


async def mark_profiles_queued(profile_ids: Iterable[str]) -> int:
    """Set scrape_progress so the UI shows queued before the worker picks them up."""
    marked = 0
    for raw in profile_ids:
        pid = str(raw or "").strip()
        if not pid:
            continue
        try:
            profile = await Profile.get(pid)
            if not profile:
                continue
            total = int(profile.posts_count or 0)
            profile.scrape_progress = {
                "active": True,
                "phase": "queued",
                "scraped_posts": 0,
                "total_posts": total,
                "posts_left": total,
                "percent": 0,
                "updated_at": datetime.utcnow().isoformat() + "Z",
            }
            profile.last_error = None
            profile.updated_at = datetime.utcnow()
            await profile.save()
            marked += 1
        except Exception:
            log.exception("mark_profiles_queued failed profile_id=%s", pid)
    return marked


async def _worker_loop() -> None:
    global _running_id, _running_started
    q = _get_queue()
    log.info("bulk scrape worker started")
    while True:
        profile_id = await q.get()
        _running_id = profile_id
        _running_started = time.time()
        try:
            profile = await Profile.get(profile_id)
            if not profile:
                log.warning("bulk scrape skipped missing profile_id=%s", profile_id)
                continue
            log.info("bulk scrape start @%s id=%s (queue=%s)", profile.username, profile_id, q.qsize())
            await scrape_profile_inline(profile)
            fresh = await Profile.get(profile_id)
            log.info(
                "bulk scrape done @%s followers=%s posts=%s status=%s",
                getattr(fresh, "username", profile.username),
                getattr(fresh, "followers", "?") if fresh else "?",
                getattr(fresh, "posts_count", "?") if fresh else "?",
                getattr(fresh, "status", "?") if fresh else "?",
            )
        except Exception:
            log.error("bulk scrape failed profile_id=%s\n%s", profile_id, traceback.format_exc())
            await _mark_profile_interrupted(
                profile_id, "Scrape worker error — click Refresh to retry."
            )
        finally:
            _running_id = None
            _running_started = None
            _pending.discard(profile_id)
            q.task_done()
            delay = _delay_seconds()
            if delay > 0 and not q.empty():
                await asyncio.sleep(delay)


def _ensure_worker() -> None:
    global _worker
    if _worker is not None and not _worker.done():
        return
    _worker = asyncio.create_task(_worker_loop(), name="instascope-bulk-scrape-worker")

    def _on_done(task: asyncio.Task) -> None:
        global _worker
        try:
            exc = task.exception()
            if exc:
                log.error("bulk scrape worker crashed: %s", exc)
        except asyncio.CancelledError:
            pass
        except Exception:
            log.error("bulk scrape worker ended\n%s", traceback.format_exc())
        _worker = None

    _worker.add_done_callback(_on_done)


async def enqueue_profile_ids(profile_ids: Iterable[str], *, force: bool = False) -> int:
    """Enqueue profile IDs for sequential scraping. Returns how many were queued.

    force=True re-queues even if the id is already pending (used by Refresh when
    a previous attempt looks stuck).
    """
    q = _get_queue()
    _ensure_worker()
    queued = 0
    async with _lock:
        for raw in profile_ids:
            pid = str(raw or "").strip()
            if not pid:
                continue
            if pid in _pending:
                if not force:
                    continue
                # Already running — don't duplicate mid-flight.
                if pid == _running_id:
                    # If the current job looks hung, leave it; timeout will free it.
                    if _running_started and (time.time() - _running_started) < _stale_seconds():
                        continue
                else:
                    # Pending but not running (orphaned set entry) — drop and re-add.
                    _pending.discard(pid)
            _pending.add(pid)
            await q.put(pid)
            queued += 1
    if queued:
        log.info("enqueued %s profile(s) for bulk scrape (pending=%s)", queued, len(_pending))
    return queued


def pending_count() -> int:
    return len(_pending)


def running_profile_id() -> str | None:
    return _running_id
