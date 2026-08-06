"""Single-profile scrape runner (Add / Refresh).

Uses a concurrency semaphore and profile leases so bulk cannot block Refresh,
and N parallel refreshes cannot storm proxies/Chromium.
"""

from __future__ import annotations

import asyncio
import logging
import os
import traceback
from datetime import datetime
from typing import Any

from app.scrape_lease import (
    acquire,
    bump_generation,
    current_generation,
    release,
)
from instascope_shared.models import Job, Profile, ProfileStatus
from instascope_shared.services.scrape_core import progress_payload, run_profile_scrape

log = logging.getLogger("instascope.api.scrape_single")

_tasks: dict[str, asyncio.Task[Any]] = {}
_lock = asyncio.Lock()
_sem: asyncio.Semaphore | None = None


def _concurrency() -> int:
    raw = (os.getenv("SCRAPE_SINGLE_CONCURRENCY") or "3").strip()
    try:
        return max(1, min(8, int(raw)))
    except ValueError:
        return 3


def _get_sem() -> asyncio.Semaphore:
    global _sem
    if _sem is None:
        _sem = asyncio.Semaphore(_concurrency())
    return _sem


async def mark_single_queued(profile: Profile) -> None:
    total = int(profile.posts_count or 0)
    profile.scrape_progress = progress_payload(
        scraped=0,
        total=total,
        phase="queued",
        active=True,
        source="single",
    )
    profile.last_error = None
    # Allow Refresh to retry handles wrongly marked unavailable (false IG 404s).
    if profile.status == ProfileStatus.UNAVAILABLE:
        profile.status = ProfileStatus.ACTIVE
    profile.updated_at = datetime.utcnow()
    await profile.save()


async def _mark_interrupted(profile_id: str, generation: int, reason: str) -> None:
    if current_generation(profile_id) != generation:
        return
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
            "source": "single",
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }
        if not profile.last_error:
            profile.last_error = reason
        profile.updated_at = datetime.utcnow()
        await profile.save()
    except Exception:
        log.exception("mark interrupted failed profile_id=%s", profile_id)


async def _run(profile_id: str, generation: int, job: Job | None) -> None:
    owned = False
    sem = _get_sem()
    await sem.acquire()
    try:
        if current_generation(profile_id) != generation:
            log.info("single scrape superseded while waiting for slot id=%s", profile_id)
            return

        profile = await Profile.get(profile_id)
        if not profile:
            log.warning("single scrape skipped missing profile_id=%s", profile_id)
            return

        owned = await acquire(profile_id, "single", generation)
        if not owned:
            log.info(
                "single scrape skipped @%s — lease held by another owner gen=%s",
                profile.username,
                generation,
            )
            return

        def is_current() -> bool:
            return current_generation(profile_id) == generation

        if not is_current():
            log.info("single scrape superseded before start profile_id=%s", profile_id)
            return

        log.info("single scrape start @%s id=%s gen=%s", profile.username, profile_id, generation)
        await run_profile_scrape(
            profile,
            source="single",
            job=job,
            generation=generation,
            is_current=is_current,
        )
        fresh = await Profile.get(profile_id)
        log.info(
            "single scrape done @%s followers=%s posts=%s status=%s",
            getattr(fresh, "username", profile.username),
            getattr(fresh, "followers", "?") if fresh else "?",
            getattr(fresh, "posts_count", "?") if fresh else "?",
            getattr(fresh, "status", "?") if fresh else "?",
        )
    except asyncio.CancelledError:
        await _mark_interrupted(
            profile_id, generation, "Scrape cancelled — click Refresh to retry."
        )
        raise
    except Exception:
        log.error("single scrape failed profile_id=%s\n%s", profile_id, traceback.format_exc())
        try:
            if current_generation(profile_id) == generation:
                profile = await Profile.get(profile_id)
                if profile:
                    prog = dict(getattr(profile, "scrape_progress", None) or {})
                    profile.scrape_progress = {
                        **prog,
                        "active": False,
                        "phase": "failed",
                        "source": "single",
                        "updated_at": datetime.utcnow().isoformat() + "Z",
                    }
                    if not profile.last_error:
                        profile.last_error = "Single scrape worker error — click Refresh to retry."
                    profile.updated_at = datetime.utcnow()
                    await profile.save()
        except Exception:
            log.exception("failed to mark single scrape error profile_id=%s", profile_id)
    finally:
        if owned:
            await release(profile_id, "single", generation)
        _tasks.pop(profile_id, None)
        sem.release()


async def schedule_single_scrape(
    profile_id: str,
    *,
    force: bool = True,
    job: Job | None = None,
) -> bool:
    """Start (or re-start) a dedicated scrape task for one profile."""
    pid = str(profile_id or "").strip()
    if not pid:
        return False

    async with _lock:
        # Bump first so any in-flight run sees is_current() == False before cancel.
        generation = bump_generation(pid)
        existing = _tasks.get(pid)
        if existing is not None and not existing.done():
            if not force:
                log.info("single scrape already running profile_id=%s", pid)
                return False
            existing.cancel()
            _tasks.pop(pid, None)

        profile = await Profile.get(pid)
        if not profile:
            return False

        await mark_single_queued(profile)
        task = asyncio.create_task(
            _run(pid, generation, job), name=f"instascope-single-scrape-{pid}"
        )
        _tasks[pid] = task

        def _on_done(t: asyncio.Task[Any]) -> None:
            if _tasks.get(pid) is t:
                _tasks.pop(pid, None)
            try:
                exc = t.exception()
                if exc:
                    log.error("single scrape task crashed profile_id=%s: %s", pid, exc)
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

        task.add_done_callback(_on_done)
        log.info("scheduled single scrape profile_id=%s gen=%s", pid, generation)
        return True


def single_scrape_running(profile_id: str) -> bool:
    t = _tasks.get(str(profile_id))
    return t is not None and not t.done()
