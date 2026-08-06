"""Sequential in-process scrape queue for bulk import/refresh.

Single Add/Refresh awaits the scrape on the request. Bulk used fire-and-forget
`asyncio.create_task` loops that often never completed (or hammered Instagram).
This queue runs one scrape at a time with a delay between jobs and keeps a
strong reference to the worker task for the life of the API process.
"""

from __future__ import annotations

import asyncio
import logging
import os
import traceback
from typing import Iterable

from instascope_shared.models import Profile
from instascope_shared.services.inline_scrape import scrape_profile_inline

log = logging.getLogger("instascope.api.scrape_queue")

_queue: asyncio.Queue[str] | None = None
_worker: asyncio.Task | None = None
_pending: set[str] = set()
_lock = asyncio.Lock()


def _delay_seconds() -> float:
    raw = (os.getenv("SCRAPE_BULK_DELAY_SECONDS") or "").strip()
    if raw:
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass
    try:
        return max(2.0, float(os.getenv("SCRAPE_DELAY_SECONDS") or "2"))
    except ValueError:
        return 3.0


def _get_queue() -> asyncio.Queue[str]:
    global _queue
    if _queue is None:
        _queue = asyncio.Queue()
    return _queue


async def _worker_loop() -> None:
    q = _get_queue()
    log.info("bulk scrape worker started")
    while True:
        profile_id = await q.get()
        try:
            profile = await Profile.get(profile_id)
            if not profile:
                log.warning("bulk scrape skipped missing profile_id=%s", profile_id)
                continue
            log.info("bulk scrape start @%s id=%s (queue=%s)", profile.username, profile_id, q.qsize())
            await scrape_profile_inline(profile)
            log.info(
                "bulk scrape done @%s followers=%s posts=%s status=%s",
                profile.username,
                getattr(profile, "followers", "?"),
                getattr(profile, "posts_count", "?"),
                getattr(profile, "status", "?"),
            )
        except Exception:
            log.error("bulk scrape failed profile_id=%s\n%s", profile_id, traceback.format_exc())
        finally:
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


async def enqueue_profile_ids(profile_ids: Iterable[str]) -> int:
    """Enqueue profile IDs for sequential scraping. Returns how many were queued."""
    q = _get_queue()
    _ensure_worker()
    queued = 0
    async with _lock:
        for raw in profile_ids:
            pid = str(raw or "").strip()
            if not pid:
                continue
            if pid in _pending:
                continue
            _pending.add(pid)
            await q.put(pid)
            queued += 1
    if queued:
        log.info("enqueued %s profile(s) for bulk scrape (pending=%s)", queued, len(_pending))
    return queued


def pending_count() -> int:
    return len(_pending)
