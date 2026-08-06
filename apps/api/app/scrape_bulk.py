"""Bulk sequential scrape queue with two-phase auto deep follow-up.

Phase 1 (sample): Import / bulk refresh — capped by SCRAPE_BULK_MAX_POSTS (default 48).
Phase 2 (deep): After a successful capped sample, automatically queue a full timeline
scrape (uncapped). Sample jobs always run before deep jobs so the roster fills fast.

Single Add/Refresh must NOT use this path — see ``scrape_single.schedule_single_scrape``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import traceback
from datetime import datetime
from typing import Any, Iterable, Literal

from bson import ObjectId

from instascope_shared.core.config import get_settings
from instascope_shared.models import Profile, ProfileStatus
from instascope_shared.services.scrape_core import progress_payload, run_profile_scrape

from app.scrape_lease import (
    acquire,
    bump_generation,
    current_generation,
    owner_of,
    release,
)

log = logging.getLogger("instascope.api.scrape_bulk")

Mode = Literal["bulk", "deep"]

_REDIS_KEY = "instascope:bulk_scrape_queue"
_REDIS_PENDING = "instascope:bulk_scrape_pending"
_REDIS_DEEP_KEY = "instascope:deep_scrape_queue"
_REDIS_DEEP_PENDING = "instascope:deep_scrape_pending"

_sample_queue: asyncio.Queue[str] | None = None
_deep_queue: asyncio.Queue[str] | None = None
_worker: asyncio.Task | None = None
_sample_pending: set[str] = set()
_deep_pending: set[str] = set()
_lock = asyncio.Lock()
_wake = asyncio.Event()
_running_id: str | None = None
_running_mode: Mode | None = None
_running_started: float | None = None
_redis: Any = None
_use_redis: bool | None = None

# Back-compat alias used by clear_stale / older callers
_pending = _sample_pending


def _delay_seconds() -> float:
    raw = (os.getenv("SCRAPE_BULK_DELAY_SECONDS") or "").strip()
    if raw:
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass
    try:
        return max(10.0, float(os.getenv("SCRAPE_DELAY_SECONDS") or "10"))
    except ValueError:
        return 10.0


def _stale_seconds() -> float:
    raw = (os.getenv("SCRAPE_STALE_SECONDS") or "600").strip()
    try:
        return max(120.0, float(raw))
    except ValueError:
        return 600.0


def _bulk_max_posts() -> int:
    raw = (os.getenv("SCRAPE_BULK_MAX_POSTS") or "48").strip()
    if not raw:
        return 48
    try:
        return max(0, int(raw))
    except ValueError:
        return 48


def _deep_followup_enabled() -> bool:
    """Auto full-scrape after capped bulk sample (default on)."""
    raw = (os.getenv("SCRAPE_BULK_DEEP_FOLLOWUP") or "1").strip().lower()
    return raw not in {"0", "false", "no", ""}


def _get_sample_queue() -> asyncio.Queue[str]:
    global _sample_queue
    if _sample_queue is None:
        _sample_queue = asyncio.Queue()
    return _sample_queue


def _get_deep_queue() -> asyncio.Queue[str]:
    global _deep_queue
    if _deep_queue is None:
        _deep_queue = asyncio.Queue()
    return _deep_queue


def _get_queue() -> asyncio.Queue[str]:
    """Back-compat: sample queue."""
    return _get_sample_queue()


async def _get_redis():
    """Optional Redis — never block more than 1s; failures disable Redis for process."""
    global _redis, _use_redis
    if _use_redis is False:
        return None
    if _redis is not None:
        return _redis
    try:
        import redis.asyncio as redis_async

        url = get_settings().redis_url
        client = redis_async.from_url(url, decode_responses=True, socket_connect_timeout=1)
        await asyncio.wait_for(client.ping(), timeout=1.0)
        _redis = client
        _use_redis = True
        log.info("bulk scrape Redis mirror ready")
        return _redis
    except Exception as exc:
        _use_redis = False
        _redis = None
        log.warning("bulk scrape Redis unavailable (%s) — memory queue only", exc)
        return None


async def _mark_profile_interrupted(profile_id: str, reason: str, *, source: str = "bulk") -> None:
    try:
        profile = await Profile.get(profile_id)
        if not profile:
            return
        prog = dict(getattr(profile, "scrape_progress", None) or {})
        profile.scrape_progress = {
            **prog,
            "active": False,
            "phase": "interrupted",
            "source": source,
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }
        if not profile.last_error:
            profile.last_error = reason
        profile.updated_at = datetime.utcnow()
        await profile.save()
    except Exception:
        log.exception("failed to mark interrupted profile_id=%s", profile_id)


def _needs_deep_followup(profile: Profile) -> bool:
    """True when the capped sample left posts on the table."""
    if not _deep_followup_enabled():
        return False
    cap = _bulk_max_posts()
    if cap <= 0:
        return False
    if profile.status in {ProfileStatus.FAILED, ProfileStatus.UNAVAILABLE}:
        return False
    prog = dict(getattr(profile, "scrape_progress", None) or {})
    phase = str(prog.get("phase") or "").lower()
    if phase in {"failed", "unavailable", "interrupted"}:
        return False
    scraped = int(prog.get("scraped_posts") or 0)
    total = int(profile.posts_count or prog.get("total_posts") or 0)
    if scraped <= 0 and total <= 0:
        return False
    if total > 0 and scraped >= total:
        return False
    # Hit the sample cap (or close) while Instagram reports more posts.
    if total > scraped:
        return True
    return scraped >= cap


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
        pid = str(profile.id)
        _sample_pending.discard(pid)
        _deep_pending.discard(pid)
    if cleared:
        log.warning("cleared %s stale scrape_progress marker(s)", cleared)
    return cleared


async def resume_incomplete_bulk_scrapes() -> int:
    try:
        profiles = await Profile.find(
            {
                "scrape_progress.source": {"$in": ["bulk", "deep"]},
                "$or": [
                    {"scrape_progress.active": True},
                    {
                        "scrape_progress.phase": {
                            "$in": [
                                "queued",
                                "queued_full",
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
    sample_ids: list[str] = []
    deep_ids: list[str] = []
    for profile in profiles:
        if profile.status in {ProfileStatus.FAILED, ProfileStatus.UNAVAILABLE}:
            continue
        prog = dict(getattr(profile, "scrape_progress", None) or {})
        phase = str(prog.get("phase") or "").lower()
        if phase in {"failed", "unavailable", "done", "interrupted"}:
            continue
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
        source = str(prog.get("source") or "bulk")
        pid = str(profile.id)
        if source == "deep" or phase == "queued_full":
            if not prog.get("active"):
                profile.scrape_progress = progress_payload(
                    scraped=int(prog.get("scraped_posts") or 0),
                    total=int(prog.get("total_posts") or profile.posts_count or 0),
                    phase="queued_full",
                    active=True,
                    source="deep",
                )
                profile.updated_at = datetime.utcnow()
                await profile.save()
            deep_ids.append(pid)
        else:
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
            sample_ids.append(pid)

    queued = 0
    if sample_ids:
        queued += await enqueue_bulk_profile_ids(sample_ids, force=True)
    if deep_ids:
        queued += await enqueue_deep_profile_ids(deep_ids, force=True)
    if queued:
        log.warning("resumed %s incomplete BULK/DEEP scrape(s)", queued)
    return queued


resume_incomplete_scrapes = resume_incomplete_bulk_scrapes


async def requeue_unfinished_bulk_profiles() -> int:
    """Re-queue interrupted / soft-failed bulk rows that never got real IG data.

    Covers the common post-import state: hundreds of profiles stuck at
    phase=interrupted with 0 followers / 0 posts after worker restarts.
    Skips UNAVAILABLE (missing IG) and profiles that already scraped successfully.
    """
    raw = (os.getenv("SCRAPE_REQUEUE_UNFINISHED") or "1").strip().lower()
    if raw in {"0", "false", "no"}:
        return 0
    try:
        profiles = await Profile.find(
            {
                "status": {"$nin": [ProfileStatus.UNAVAILABLE, ProfileStatus.PAUSED]},
                "$or": [
                    {"scrape_progress.phase": "interrupted"},
                    {
                        "status": ProfileStatus.FAILED,
                        "followers": {"$lte": 0},
                        "posts_count": {"$lte": 0},
                    },
                    {
                        "scrape_progress.source": {"$in": ["bulk", "deep"]},
                        "followers": {"$lte": 0},
                        "posts_count": {"$lte": 0},
                        "last_success_at": None,
                    },
                ],
            }
        ).to_list()
    except Exception:
        log.exception("requeue_unfinished_bulk_profiles query failed")
        return 0

    ids: list[str] = []
    for profile in profiles:
        if profile.status == ProfileStatus.UNAVAILABLE:
            continue
        if profile.last_success_at and (profile.followers or profile.posts_count):
            continue
        prog = dict(getattr(profile, "scrape_progress", None) or {})
        phase = str(prog.get("phase") or "").lower()
        if phase == "unavailable":
            continue
        # Clear stale failed badge so UI shows queued/scraping again.
        profile.status = ProfileStatus.ACTIVE
        profile.last_error = None
        profile.scrape_progress = progress_payload(
            scraped=0,
            total=int(profile.posts_count or 0),
            phase="queued",
            active=True,
            source="bulk",
        )
        profile.updated_at = datetime.utcnow()
        await profile.save()
        ids.append(str(profile.id))

    if not ids:
        return 0
    queued = await enqueue_bulk_profile_ids(ids, force=True)
    if queued:
        log.warning(
            "re-queued %s unfinished bulk profile(s) (zeros/interrupted/failed)",
            queued,
        )
    return queued


async def mark_profiles_queued(profile_ids: Iterable[str]) -> int:
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


async def _mirror_redis_add(pid: str, *, deep: bool = False) -> None:
    r = await _get_redis()
    if r is None:
        return
    try:
        if deep:
            await r.sadd(_REDIS_DEEP_PENDING, pid)
            await r.rpush(_REDIS_DEEP_KEY, pid)
        else:
            await r.sadd(_REDIS_PENDING, pid)
            await r.rpush(_REDIS_KEY, pid)
    except Exception:
        log.exception("redis mirror add failed pid=%s deep=%s", pid, deep)


async def _mirror_redis_done(pid: str, *, deep: bool = False) -> None:
    r = await _get_redis()
    if r is None:
        return
    try:
        if deep:
            await r.srem(_REDIS_DEEP_PENDING, pid)
            await r.lrem(_REDIS_DEEP_KEY, 0, pid)
        else:
            await r.srem(_REDIS_PENDING, pid)
            await r.lrem(_REDIS_KEY, 0, pid)
    except Exception:
        pass


async def _hydrate_queue_from_redis() -> int:
    r = await _get_redis()
    if r is None:
        return 0
    moved = 0
    try:
        while True:
            pid = await asyncio.wait_for(r.lpop(_REDIS_KEY), timeout=1.0)
            if not pid:
                break
            pid = str(pid)
            async with _lock:
                if pid not in _sample_pending:
                    _sample_pending.add(pid)
                    await _get_sample_queue().put(pid)
                    moved += 1
            try:
                await r.srem(_REDIS_PENDING, pid)
            except Exception:
                pass
        while True:
            pid = await asyncio.wait_for(r.lpop(_REDIS_DEEP_KEY), timeout=1.0)
            if not pid:
                break
            pid = str(pid)
            async with _lock:
                if pid not in _deep_pending:
                    _deep_pending.add(pid)
                    await _get_deep_queue().put(pid)
                    moved += 1
            try:
                await r.srem(_REDIS_DEEP_PENDING, pid)
            except Exception:
                pass
    except Exception:
        log.exception("hydrate from Redis failed")
    if moved:
        log.warning("hydrated %s bulk/deep id(s) from Redis", moved)
        _wake.set()
    return moved


async def _requeue_later(profile_id: str, *, mode: Mode) -> None:
    await asyncio.sleep(3)
    if mode == "deep":
        await enqueue_deep_profile_ids([profile_id], force=True)
    else:
        await enqueue_bulk_profile_ids([profile_id], force=True)


async def _wait_next_job() -> tuple[str, Mode]:
    """Block until work appears. Prefer sample (phase 1) over deep (phase 2)."""
    while True:
        async with _lock:
            try:
                pid = _get_sample_queue().get_nowait()
                return pid, "bulk"
            except asyncio.QueueEmpty:
                pass
            try:
                pid = _get_deep_queue().get_nowait()
                return pid, "deep"
            except asyncio.QueueEmpty:
                pass
        _wake.clear()
        try:
            await asyncio.wait_for(_wake.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            continue


async def _maybe_enqueue_deep_after_sample(profile_id: str) -> None:
    profile = await Profile.get(profile_id)
    if not profile or not _needs_deep_followup(profile):
        return
    prog = dict(getattr(profile, "scrape_progress", None) or {})
    scraped = int(prog.get("scraped_posts") or 0)
    total = int(profile.posts_count or prog.get("total_posts") or 0)
    profile.scrape_progress = progress_payload(
        scraped=scraped,
        total=total,
        phase="queued_full",
        active=True,
        source="deep",
    )
    profile.updated_at = datetime.utcnow()
    await profile.save()
    n = await enqueue_deep_profile_ids([profile_id], force=False)
    if n:
        log.info(
            "queued DEEP full scrape after sample @%s scraped=%s total=%s",
            profile.username,
            scraped,
            total,
        )


async def _worker_loop() -> None:
    global _running_id, _running_mode, _running_started
    log.info(
        "bulk scrape worker started (two-phase deep follow-up=%s cap=%s)",
        _deep_followup_enabled(),
        _bulk_max_posts(),
    )
    try:
        await _hydrate_queue_from_redis()
    except Exception:
        log.exception("initial redis hydrate failed — continuing with memory queue")

    while True:
        profile_id, mode = await _wait_next_job()
        _running_id = profile_id
        _running_mode = mode
        _running_started = time.time()
        deferred = False
        owned = False
        generation: int | None = None
        source = "deep" if mode == "deep" else "bulk"
        try:
            profile = await Profile.get(profile_id)
            if not profile:
                log.warning("%s scrape skipped missing profile_id=%s", mode, profile_id)
            elif profile.status == ProfileStatus.UNAVAILABLE:
                log.info(
                    "%s scrape skipped @%s — Instagram profile does not exist",
                    mode,
                    profile.username,
                )
                prog = dict(getattr(profile, "scrape_progress", None) or {})
                if prog.get("active") or str(prog.get("phase") or "") not in {
                    "unavailable",
                    "failed",
                }:
                    profile.scrape_progress = {
                        **prog,
                        "active": False,
                        "phase": "unavailable",
                        "updated_at": datetime.utcnow().isoformat() + "Z",
                    }
                    profile.updated_at = datetime.utcnow()
                    await profile.save()
            else:
                from app.scrape_single import single_scrape_running

                if single_scrape_running(profile_id) or owner_of(profile_id) == "single":
                    log.info(
                        "%s scrape deferred @%s — single owns lease",
                        mode,
                        profile.username,
                    )
                    deferred = True
                    asyncio.create_task(
                        _requeue_later(profile_id, mode=mode),
                        name=f"{mode}-requeue-{profile_id}",
                    )
                else:
                    generation = bump_generation(profile_id)
                    owned = await acquire(profile_id, source, generation)
                    if not owned:
                        log.info(
                            "%s scrape deferred @%s — lease not acquired",
                            mode,
                            profile.username,
                        )
                        deferred = True
                        asyncio.create_task(
                            _requeue_later(profile_id, mode=mode),
                            name=f"{mode}-requeue-{profile_id}",
                        )
                    else:
                        gen = generation

                        def is_current() -> bool:
                            return current_generation(profile_id) == gen

                        log.info(
                            "%s scrape START @%s id=%s gen=%s sample_pending=%s deep_pending=%s",
                            mode.upper(),
                            profile.username,
                            profile_id,
                            generation,
                            len(_sample_pending),
                            len(_deep_pending),
                        )
                        await run_profile_scrape(
                            profile,
                            source=source,  # type: ignore[arg-type]
                            generation=generation,
                            is_current=is_current,
                        )
                        fresh = await Profile.get(profile_id)
                        log.info(
                            "%s scrape DONE @%s followers=%s posts=%s status=%s",
                            mode.upper(),
                            getattr(fresh, "username", profile.username),
                            getattr(fresh, "followers", "?") if fresh else "?",
                            getattr(fresh, "posts_count", "?") if fresh else "?",
                            getattr(fresh, "status", "?") if fresh else "?",
                        )
                        if mode == "bulk" and fresh:
                            await _maybe_enqueue_deep_after_sample(profile_id)
        except Exception:
            log.error(
                "%s scrape failed profile_id=%s\n%s",
                mode,
                profile_id,
                traceback.format_exc(),
            )
            if not deferred:
                await _mark_profile_interrupted(
                    profile_id,
                    f"{'Deep' if mode == 'deep' else 'Bulk'} scrape worker error — click Refresh to retry.",
                    source=source,
                )
        finally:
            if owned and generation is not None:
                await release(profile_id, source, generation)
            _running_id = None
            _running_mode = None
            _running_started = None
            if not deferred:
                if mode == "deep":
                    _deep_pending.discard(profile_id)
                    await _mirror_redis_done(profile_id, deep=True)
                else:
                    _sample_pending.discard(profile_id)
                    await _mirror_redis_done(profile_id, deep=False)
            delay = _delay_seconds()
            has_more = (
                not _get_sample_queue().empty()
                or not _get_deep_queue().empty()
                or bool(_sample_pending)
                or bool(_deep_pending)
            )
            if delay > 0 and not deferred and has_more:
                await asyncio.sleep(delay)


def ensure_bulk_worker() -> None:
    """Start the bulk worker if it is not running (safe to call often)."""
    global _worker
    if _worker is not None and not _worker.done():
        return
    _worker = asyncio.create_task(_worker_loop(), name="instascope-bulk-scrape-worker")
    log.info("bulk scrape worker task created")

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
        if (
            _sample_pending
            or _deep_pending
            or (_sample_queue is not None and not _sample_queue.empty())
            or (_deep_queue is not None and not _deep_queue.empty())
        ):
            log.warning("restarting bulk scrape worker (queue not empty)")
            ensure_bulk_worker()

    _worker.add_done_callback(_on_done)


_ensure_worker = ensure_bulk_worker


async def enqueue_bulk_profile_ids(profile_ids: Iterable[str], *, force: bool = False) -> int:
    """Enqueue profile IDs for phase-1 sample scrape."""
    ensure_bulk_worker()
    queued = 0
    async with _lock:
        for raw in profile_ids:
            pid = str(raw or "").strip()
            if not pid:
                continue
            if pid in _sample_pending:
                if not force:
                    continue
                if pid == _running_id and _running_mode == "bulk":
                    if _running_started and (time.time() - _running_started) < _stale_seconds():
                        continue
                else:
                    _sample_pending.discard(pid)
            # Don't also sit in deep for the same id while sample re-runs.
            _deep_pending.discard(pid)
            _sample_pending.add(pid)
            await _get_sample_queue().put(pid)
            queued += 1
    if queued:
        _wake.set()
        log.info(
            "enqueued %s profile(s) for BULK sample (sample_pending=%s deep_pending=%s)",
            queued,
            len(_sample_pending),
            len(_deep_pending),
        )
        for raw in profile_ids:
            pid = str(raw or "").strip()
            if pid:
                asyncio.create_task(_mirror_redis_add(pid, deep=False), name=f"redis-mirror-{pid}")
    return queued


async def enqueue_deep_profile_ids(profile_ids: Iterable[str], *, force: bool = False) -> int:
    """Enqueue profile IDs for phase-2 full timeline scrape."""
    if not _deep_followup_enabled() and not force:
        return 0
    ensure_bulk_worker()
    queued = 0
    async with _lock:
        for raw in profile_ids:
            pid = str(raw or "").strip()
            if not pid:
                continue
            # Prefer finishing sample first if somehow both requested.
            if pid in _sample_pending and not force:
                continue
            if pid in _deep_pending:
                if not force:
                    continue
                if pid == _running_id and _running_mode == "deep":
                    if _running_started and (time.time() - _running_started) < _stale_seconds():
                        continue
                else:
                    _deep_pending.discard(pid)
            _deep_pending.add(pid)
            await _get_deep_queue().put(pid)
            queued += 1
    if queued:
        _wake.set()
        log.info(
            "enqueued %s profile(s) for DEEP full scrape (deep_pending=%s)",
            queued,
            len(_deep_pending),
        )
        for raw in profile_ids:
            pid = str(raw or "").strip()
            if pid:
                asyncio.create_task(
                    _mirror_redis_add(pid, deep=True), name=f"redis-deep-mirror-{pid}"
                )
    return queued


enqueue_profile_ids = enqueue_bulk_profile_ids


def pending_count() -> int:
    return len(_sample_pending) + len(_deep_pending)


def sample_pending_count() -> int:
    return len(_sample_pending)


def deep_pending_count() -> int:
    return len(_deep_pending)


def running_profile_id() -> str | None:
    return _running_id


def running_mode() -> Mode | None:
    return _running_mode
