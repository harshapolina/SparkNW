"""Shared Instagram scrape core.

Single-profile and bulk paths both call ``run_profile_scrape``.
Do not put queue / scheduling logic here — keep that in the API runners.
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime
from typing import Any, Callable, Literal

from instascope_shared.core.config import get_settings
from instascope_shared.models import Job, JobStatus, JobType, Profile
from instascope_shared.services.scrape_pipeline import apply_scrape_result, mark_scrape_failed
from instascope_scraper.caps import caps_for_api, use_caps
from instascope_scraper.profile import ScrapeError, scrape_profile
from instascope_scraper.proxy_pool import next_proxy, pool_size
from instascope_scraper.types import parse_proxy_url

ScrapeSource = Literal["single", "bulk", "deep"]

_PROGRESS_INTERVAL_S = 20.0


def _job_timeout_seconds(*, max_posts: int = 0) -> float:
    """Wall-clock limit for one scrape job.

    Uncapped / cohort scrapes need far more than 8 minutes when Instagram or the
    proxy is slow. A low ``SCRAPE_JOB_TIMEOUT_SECONDS`` (e.g. 480) used to kill
    jobs still in ``http_profile`` and leave Failed + empty Insights.
    """
    raw = (os.getenv("SCRAPE_JOB_TIMEOUT_SECONDS") or "").strip()
    configured: float | None = None
    if raw:
        try:
            configured = max(60.0, float(raw))
        except ValueError:
            configured = None

    if max_posts > 0:
        # Capped bulk sample — finish faster.
        auto = float(max(300, min(900, 120 + max_posts * 2)))
        return configured if configured is not None else auto

    # Single / deep / uncapped — allow long HTTP pagination + retries.
    auto = 2700.0
    if configured is None:
        return auto
    # Floor: never let a too-aggressive env abort mid-profile fetch.
    return max(configured, 900.0)

def progress_payload(
    *,
    scraped: int,
    total: int,
    phase: str,
    active: bool = True,
    source: ScrapeSource | None = None,
) -> dict[str, Any]:
    total_n = max(0, int(total or 0))
    scraped_n = max(0, int(scraped or 0))
    if total_n > 0:
        percent = min(100, int(round(100 * scraped_n / total_n)))
    else:
        percent = 0 if active else 100
    left = max(0, total_n - scraped_n) if total_n > 0 else 0
    out: dict[str, Any] = {
        "active": active,
        "phase": phase,
        "scraped_posts": scraped_n,
        "total_posts": total_n,
        "posts_left": left,
        "percent": percent,
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }
    if source:
        out["source"] = source
    return out


async def _resolve_job(
    profile: Profile,
    *,
    source: ScrapeSource,
    job: Job | None,
    generation: int | None,
) -> Job:
    """Reuse a PENDING job from the router when present; otherwise create one."""
    now = datetime.utcnow()
    if job is None:
        pending = (
            await Job.find(
                Job.profile_id == str(profile.id),
                Job.status == JobStatus.PENDING,
                Job.job_type == JobType.SCRAPE_PROFILE,
            )
            .sort([("created_at", -1)])
            .first_or_none()
        )
        job = pending
    if job is None:
        meta: dict[str, Any] = {"phase": "starting", "source": source}
        if generation is not None:
            meta["generation"] = int(generation)
        job = Job(
            user_id=profile.user_id,
            profile_id=str(profile.id),
            job_type=JobType.SCRAPE_PROFILE,
            status=JobStatus.RUNNING,
            priority=1,
            started_at=now,
            attempts=1,
            meta=meta,
        )
        await job.insert()
        return job

    job.status = JobStatus.RUNNING
    job.started_at = now
    job.attempts = max(1, int(job.attempts or 0) + 1)
    meta = dict(job.meta or {})
    meta["phase"] = "starting"
    meta["source"] = source
    if generation is not None:
        meta["generation"] = int(generation)
    job.meta = meta
    job.updated_at = now
    await job.save()
    return job


async def run_profile_scrape(
    profile: Profile,
    *,
    source: ScrapeSource = "single",
    job: Job | None = None,
    generation: int | None = None,
    is_current: Callable[[], bool] | None = None,
) -> Job:
    """Run one live Instagram scrape and persist results.

    ``is_current`` should return False when the caller cancelled / superseded this
    run (stale generation). Shared code must not import API lease modules.
    """

    def _current() -> bool:
        if is_current is None:
            return True
        try:
            return bool(is_current())
        except Exception:  # noqa: BLE001
            return False

    try:
        from instascope_shared.services.app_config import apply_proxy_config_to_env

        await apply_proxy_config_to_env()
    except Exception:
        pass

    settings = get_settings()
    job = await _resolve_job(profile, source=source, job=job, generation=generation)

    if not _current():
        job.status = JobStatus.CANCELLED
        job.finished_at = datetime.utcnow()
        job.error_message = "Superseded by a newer scrape"
        job.updated_at = datetime.utcnow()
        await job.save()
        return job

    proxy = next_proxy() if pool_size() > 0 else parse_proxy_url(settings.scrape_proxy_url)
    last_progress = progress_payload(
        scraped=0,
        total=int(profile.posts_count or 0),
        phase="starting",
        source=source,
    )
    last_profile_save = 0.0
    last_phase = "starting"

    async def _save_profile_progress(payload: dict[str, Any], *, force: bool = False) -> None:
        nonlocal last_profile_save
        now_m = time.monotonic()
        if not force and (now_m - last_profile_save) < _PROGRESS_INTERVAL_S:
            return
        profile.scrape_progress = payload
        profile.updated_at = datetime.utcnow()
        await profile.save()
        last_profile_save = now_m

    async def _save_job_meta(payload: dict[str, Any]) -> None:
        meta = dict(job.meta or {})
        meta.update(payload)
        job.meta = meta
        job.updated_at = datetime.utcnow()
        await job.save()

    profile.scrape_progress = last_progress
    profile.updated_at = datetime.utcnow()
    await profile.save()
    last_profile_save = time.monotonic()
    await _save_job_meta(last_progress)

    async def on_progress(info: dict[str, Any]) -> None:
        nonlocal last_progress, last_phase
        if not _current():
            return
        scraped = int(info.get("scraped_posts") or info.get("scraped") or 0)
        total = int(info.get("total_posts") or info.get("total") or 0)
        phase = str(info.get("phase") or "scraping")
        phase_changed = phase != last_phase
        last_phase = phase
        last_progress = progress_payload(
            scraped=scraped, total=total, phase=phase, active=True, source=source
        )
        await _save_profile_progress(last_progress, force=phase_changed)
        if phase_changed:
            await _save_job_meta(last_progress)

    async def _heartbeat() -> None:
        while True:
            await asyncio.sleep(_PROGRESS_INTERVAL_S)
            if not _current():
                return
            payload = dict(last_progress)
            payload["updated_at"] = datetime.utcnow().isoformat() + "Z"
            payload["active"] = True
            payload["source"] = source
            try:
                await _save_profile_progress(payload, force=True)
            except Exception:  # noqa: BLE001
                return

    caps = caps_for_api(source)
    timeout_s = _job_timeout_seconds(max_posts=int(caps.max_posts or 0))
    with use_caps(caps):
        heartbeat = asyncio.create_task(
            _heartbeat(), name=f"scrape-hb-{source}-{profile.username}"
        )
        try:
            try:
                result = await asyncio.wait_for(
                    scrape_profile(
                        profile.username,
                        headless=settings.scrape_headless,
                        proxy=proxy,
                        delay_seconds=settings.scrape_delay_seconds,
                        live=True,
                        on_progress=on_progress,
                        caps=caps,
                    ),
                    timeout=timeout_s,
                )
            except asyncio.TimeoutError as exc:
                raise ScrapeError(
                    f"Scrape timed out after {int(timeout_s)}s "
                    f"(Instagram/proxy too slow). Try Refresh again."
                ) from exc

            if not _current():
                job.status = JobStatus.CANCELLED
                job.finished_at = datetime.utcnow()
                job.error_message = "Superseded by a newer scrape"
                await job.save()
                return job

            saving = progress_payload(
                scraped=len(result.posts),
                total=int(result.posts_count or len(result.posts)),
                phase="saving",
                active=True,
                source=source,
            )
            last_progress = saving
            await _save_profile_progress(saving, force=True)
            await _save_job_meta(saving)

            if not _current():
                return job

            await apply_scrape_result(job=job, profile=profile, result=result.to_dict())

            if not _current():
                return job

            profile.scrape_progress = progress_payload(
                scraped=len(result.posts),
                total=int(result.posts_count or len(result.posts)),
                phase="done",
                active=False,
                source=source,
            )
            profile.updated_at = datetime.utcnow()
            await profile.save()
        except asyncio.CancelledError:
            if _current():
                profile.scrape_progress = progress_payload(
                    scraped=int(last_progress.get("scraped_posts") or 0),
                    total=int(last_progress.get("total_posts") or profile.posts_count or 0),
                    phase="interrupted",
                    active=False,
                    source=source,
                )
                profile.last_error = "Scrape cancelled — click Refresh to retry."
                profile.updated_at = datetime.utcnow()
                await profile.save()
                job.status = JobStatus.CANCELLED
                job.finished_at = datetime.utcnow()
                job.error_message = "Cancelled"
                await job.save()
            raise
        except ScrapeError as exc:
            if not _current():
                return job
            await mark_scrape_failed(job, profile, str(exc), unavailable=exc.unavailable)
            if not _current():
                return job
            # mark_scrape_failed already cleared progress; keep phase explicit for UI.
            phase = "unavailable" if exc.unavailable else "failed"
            profile.scrape_progress = progress_payload(
                scraped=0,
                total=int(profile.posts_count or 0),
                phase=phase,
                active=False,
                source=source,
            )
            await profile.save()
        except Exception as exc:  # noqa: BLE001
            if not _current():
                return job
            await mark_scrape_failed(job, profile, str(exc))
            if not _current():
                return job
            profile.scrape_progress = progress_payload(
                scraped=0,
                total=int(profile.posts_count or 0),
                phase="failed",
                active=False,
                source=source,
            )
            await profile.save()
        finally:
            heartbeat.cancel()
            try:
                await heartbeat
            except asyncio.CancelledError:
                pass
    return job
