"""Bulk-only sequential scrape queue.

Import-center / bulk refresh use this path. Single Add/Refresh must NOT use it —
see ``scrape_single.schedule_single_scrape``.

Both paths call the same core: ``instascope_shared.services.scrape_core.run_profile_scrape``.
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
from instascope_shared.services.scrape_core import progress_payload, run_profile_scrape

log = logging.getLogger("instascope.api.scrape_bulk")

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
            "source": "bulk",
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


async def resume_incomplete_bulk_scrapes() -> int:
    """Re-enqueue BULK scrapes only after API restart (never touch single-path jobs)."""
    try:
        profiles = await Profile.find(
            {
                "scrape_progress.source": "bulk",
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
                ],
            }
        ).to_list()
    except Exception:
        log.exception("resume_incomplete_bulk_scrapes query failed")
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
                age_ok = age < _stale_seconds()
            except Exception:
                age_ok = True
        if not age_ok:
            continue
        if not prog.get("active"):
            profile.scrape_progress = progress_payload(
                scraped=int(prog.get("scraped_posts") or 0),
                total=int(prog.get("total_posts") or profile.posts_count or 0),
                phase="queued",
                active=True,
                source="bulk",
            )
            profile.updated_at = datetime.utcnow()
            await profile.save()
        to_resume.append(str(profile.id))

    if not to_resume:
        return 0
    queued = await enqueue_bulk_profile_ids(to_resume, force=True)
    if queued:
        log.warning("resumed %s incomplete BULK scrape(s) after API restart", queued)
    return queued


# Back-compat alias used by main.py
resume_incomplete_scrapes = resume_incomplete_bulk_scrapes


async def mark_profiles_queued(profile_ids: Iterable[str]) -> int:
    """Mark bulk jobs as queued (source=bulk) before the worker picks them up."""
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
            profile.scrape_progress = progress_payload(
                scraped=0,
                total=total,
                phase="queued",
                active=True,
                source="bulk",
            )
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
        deferred = False
        try:
            profile = await Profile.get(profile_id)
            if not profile:
                log.warning("bulk scrape skipped missing profile_id=%s", profile_id)
            else:
                from app.scrape_single import single_scrape_running

                if single_scrape_running(profile_id):
                    log.info(
                        "bulk scrape deferred @%s — single scrape owns this profile",
                        profile.username,
                    )
                    deferred = True
                    await asyncio.sleep(5)
                    await q.put(profile_id)
                else:
                    log.info(
                        "bulk scrape start @%s id=%s (queue=%s)",
                        profile.username,
                        profile_id,
                        q.qsize(),
                    )
                    await run_profile_scrape(profile, source="bulk")
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
            if not deferred:
                await _mark_profile_interrupted(
                    profile_id, "Bulk scrape worker error — click Refresh to retry."
                )
        finally:
            _running_id = None
            _running_started = None
            if not deferred:
                _pending.discard(profile_id)
            q.task_done()
            delay = _delay_seconds()
            if delay > 0 and not q.empty() and not deferred:
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


async def enqueue_bulk_profile_ids(profile_ids: Iterable[str], *, force: bool = False) -> int:
    """Enqueue profile IDs for sequential BULK scraping only."""
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
                if pid == _running_id:
                    if _running_started and (time.time() - _running_started) < _stale_seconds():
                        continue
                else:
                    _pending.discard(pid)
            _pending.add(pid)
            await q.put(pid)
            queued += 1
    if queued:
        log.info("enqueued %s profile(s) for BULK scrape (pending=%s)", queued, len(_pending))
    return queued


# Back-compat names (bulk import used these)
enqueue_profile_ids = enqueue_bulk_profile_ids


def pending_count() -> int:
    return len(_pending)


def running_profile_id() -> str | None:
    return _running_id
