"""Bulk-only sequential scrape queue.

Import-center / bulk refresh use this path. Single Add/Refresh must NOT use it —
see ``scrape_single.schedule_single_scrape``.

Execution plane: in-API worker only (Celery path intentionally unused).
Queue state prefers Redis when REDIS_URL is reachable; falls back to in-process
asyncio.Queue (document: run a single API worker if Redis is unavailable).
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import traceback
from datetime import datetime
from typing import Any, Iterable

from bson import ObjectId

from instascope_shared.core.config import get_settings
from instascope_shared.models import Profile
from instascope_shared.services.scrape_core import progress_payload, run_profile_scrape

from app.scrape_lease import (
    acquire,
    bump_generation,
    current_generation,
    owner_of,
    release,
)

log = logging.getLogger("instascope.api.scrape_bulk")

_REDIS_KEY = "instascope:bulk_scrape_queue"
_REDIS_PENDING = "instascope:bulk_scrape_pending"

_queue: asyncio.Queue[str] | None = None
_worker: asyncio.Task | None = None
_pending: set[str] = set()
_lock = asyncio.Lock()
_running_id: str | None = None
_running_started: float | None = None
_redis: Any = None
_use_redis: bool | None = None


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


async def _get_redis():
    global _redis, _use_redis
    if _use_redis is False:
        return None
    if _redis is not None:
        return _redis
    try:
        import redis.asyncio as redis_async

        url = get_settings().redis_url
        client = redis_async.from_url(url, decode_responses=True)
        await client.ping()
        _redis = client
        _use_redis = True
        log.info("bulk scrape queue using Redis at %s", url.split("@")[-1])
        return _redis
    except Exception as exc:
        _use_redis = False
        _redis = None
        log.warning("bulk scrape queue Redis unavailable (%s) — using in-memory queue", exc)
        return None


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
        r = await _get_redis()
        if r:
            try:
                await r.srem(_REDIS_PENDING, str(profile.id))
            except Exception:
                pass
    if cleared:
        log.warning("cleared %s stale scrape_progress marker(s)", cleared)
    return cleared


async def resume_incomplete_bulk_scrapes() -> int:
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


resume_incomplete_scrapes = resume_incomplete_bulk_scrapes


async def mark_profiles_queued(profile_ids: Iterable[str]) -> int:
    """Batch-mark bulk jobs as queued via update_many."""
    ids = [str(pid).strip() for pid in profile_ids if str(pid or "").strip()]
    if not ids:
        return 0
    now = datetime.utcnow()
    oids: list[ObjectId] = []
    for pid in ids:
        try:
            oids.append(ObjectId(pid))
        except Exception:
            continue
    if not oids:
        return 0
    payload = progress_payload(
        scraped=0, total=0, phase="queued", active=True, source="bulk"
    )
    # Keep per-profile total_posts when possible via pipeline is heavy; set zeros
    # then worker will refresh. Prefer one round-trip.
    result = await Profile.get_motor_collection().update_many(
        {"_id": {"$in": oids}},
        {
            "$set": {
                "scrape_progress": payload,
                "last_error": None,
                "updated_at": now,
            }
        },
    )
    return int(result.matched_count or 0)


async def _pop_next() -> tuple[str, bool]:
    """Return (profile_id, from_memory_queue)."""
    r = await _get_redis()
    if r is not None:
        while True:
            q = _get_queue()
            if not q.empty():
                return await q.get(), True
            item = await r.blpop(_REDIS_KEY, timeout=1)
            if item:
                _key, pid = item
                return str(pid), False
            await asyncio.sleep(0.05)
    return await _get_queue().get(), True


async def _worker_loop() -> None:
    global _running_id, _running_started
    log.info("bulk scrape worker started")
    while True:
        profile_id, from_memory = await _pop_next()
        _running_id = profile_id
        _running_started = time.time()
        deferred = False
        owned = False
        generation: int | None = None
        try:
            profile = await Profile.get(profile_id)
            if not profile:
                log.warning("bulk scrape skipped missing profile_id=%s", profile_id)
            else:
                from app.scrape_single import single_scrape_running

                if single_scrape_running(profile_id) or owner_of(profile_id) == "single":
                    log.info(
                        "bulk scrape deferred @%s — single scrape owns this profile",
                        profile.username,
                    )
                    deferred = True
                    await asyncio.sleep(5)
                    await enqueue_bulk_profile_ids([profile_id], force=True)
                else:
                    generation = bump_generation(profile_id)
                    owned = await acquire(profile_id, "bulk", generation)
                    if not owned:
                        log.info(
                            "bulk scrape deferred @%s — lease not acquired",
                            profile.username,
                        )
                        deferred = True
                        await asyncio.sleep(5)
                        await enqueue_bulk_profile_ids([profile_id], force=True)
                    else:
                        gen = generation

                        def is_current() -> bool:
                            return current_generation(profile_id) == gen

                        log.info(
                            "bulk scrape start @%s id=%s gen=%s",
                            profile.username,
                            profile_id,
                            generation,
                        )
                        await run_profile_scrape(
                            profile,
                            source="bulk",
                            generation=generation,
                            is_current=is_current,
                        )
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
            if owned and generation is not None:
                await release(profile_id, "bulk", generation)
            _running_id = None
            _running_started = None
            if not deferred:
                _pending.discard(profile_id)
                r = await _get_redis()
                if r:
                    try:
                        await r.srem(_REDIS_PENDING, profile_id)
                    except Exception:
                        pass
            if from_memory:
                try:
                    _get_queue().task_done()
                except Exception:
                    pass
            delay = _delay_seconds()
            if delay > 0 and not deferred:
                r = await _get_redis()
                pending_more = bool(_pending)
                if r is not None:
                    try:
                        pending_more = pending_more or (await r.llen(_REDIS_KEY) > 0)
                    except Exception:
                        pass
                if pending_more:
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
    _ensure_worker()
    r = await _get_redis()
    queued = 0
    async with _lock:
        for raw in profile_ids:
            pid = str(raw or "").strip()
            if not pid:
                continue
            if r is not None:
                try:
                    if not force and await r.sismember(_REDIS_PENDING, pid):
                        continue
                    if pid == _running_id and not force:
                        continue
                    await r.sadd(_REDIS_PENDING, pid)
                    await r.rpush(_REDIS_KEY, pid)
                    _pending.add(pid)
                    queued += 1
                    continue
                except Exception:
                    log.exception("redis enqueue failed for %s — memory fallback", pid)

            if pid in _pending:
                if not force:
                    continue
                if pid == _running_id:
                    if _running_started and (time.time() - _running_started) < _stale_seconds():
                        continue
                else:
                    _pending.discard(pid)
            _pending.add(pid)
            await _get_queue().put(pid)
            queued += 1
    if queued:
        log.info("enqueued %s profile(s) for BULK scrape (pending=%s)", queued, len(_pending))
    return queued


enqueue_profile_ids = enqueue_bulk_profile_ids


def pending_count() -> int:
    return len(_pending)


def running_profile_id() -> str | None:
    return _running_id
