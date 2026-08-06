"""Single-profile scrape runner.

Add / Refresh call this path. It does NOT share the bulk sequential queue, so a
large import cannot block or poison a single profile refresh.
"""

from __future__ import annotations

import asyncio
import logging
import traceback
from datetime import datetime
from typing import Any

from instascope_shared.models import Profile
from instascope_shared.services.scrape_core import progress_payload, run_profile_scrape

log = logging.getLogger("instascope.api.scrape_single")

# Keep strong refs so background tasks are not GC'd.
_tasks: dict[str, asyncio.Task[Any]] = {}
_lock = asyncio.Lock()


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
    profile.updated_at = datetime.utcnow()
    await profile.save()


async def _run(profile_id: str) -> None:
    try:
        profile = await Profile.get(profile_id)
        if not profile:
            log.warning("single scrape skipped missing profile_id=%s", profile_id)
            return
        log.info("single scrape start @%s id=%s", profile.username, profile_id)
        await run_profile_scrape(profile, source="single")
        fresh = await Profile.get(profile_id)
        log.info(
            "single scrape done @%s followers=%s posts=%s status=%s",
            getattr(fresh, "username", profile.username),
            getattr(fresh, "followers", "?") if fresh else "?",
            getattr(fresh, "posts_count", "?") if fresh else "?",
            getattr(fresh, "status", "?") if fresh else "?",
        )
    except Exception:
        log.error("single scrape failed profile_id=%s\n%s", profile_id, traceback.format_exc())
        try:
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
        _tasks.pop(profile_id, None)


async def schedule_single_scrape(profile_id: str, *, force: bool = True) -> bool:
    """Start (or re-start) a dedicated scrape task for one profile.

    Returns True if a new task was scheduled.
    """
    pid = str(profile_id or "").strip()
    if not pid:
        return False

    async with _lock:
        existing = _tasks.get(pid)
        if existing is not None and not existing.done():
            if not force:
                log.info("single scrape already running profile_id=%s", pid)
                return False
            # Force refresh: drop the old task handle. Cancel is best-effort;
            # do not await (would block the HTTP refresh for minutes).
            existing.cancel()
            _tasks.pop(pid, None)

        profile = await Profile.get(pid)
        if not profile:
            return False
        await mark_single_queued(profile)
        task = asyncio.create_task(_run(pid), name=f"instascope-single-scrape-{pid}")
        _tasks[pid] = task

        def _on_done(t: asyncio.Task[Any]) -> None:
            # Only clear if this task is still the registered one.
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
        log.info("scheduled single scrape profile_id=%s", pid)
        return True


def single_scrape_running(profile_id: str) -> bool:
    t = _tasks.get(str(profile_id))
    return t is not None and not t.done()
