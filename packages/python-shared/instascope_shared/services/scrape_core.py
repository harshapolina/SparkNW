"""Shared Instagram scrape core.

Single-profile and bulk paths both call ``run_profile_scrape``.
Do not put queue / scheduling logic here — keep that in the API runners.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator, Literal

from instascope_shared.core.config import get_settings
from instascope_shared.models import Job, JobStatus, JobType, Profile
from instascope_shared.services.scrape_pipeline import apply_scrape_result, mark_scrape_failed
from instascope_scraper.profile import ScrapeError, scrape_profile
from instascope_scraper.proxy_pool import next_proxy, pool_size
from instascope_scraper.types import parse_proxy_url

ScrapeSource = Literal["single", "bulk"]


def _job_timeout_seconds() -> float:
    raw = (os.getenv("SCRAPE_JOB_TIMEOUT_SECONDS") or "480").strip()
    try:
        return max(60.0, float(raw))
    except ValueError:
        return 480.0


@contextmanager
def _scrape_caps() -> Iterator[None]:
    """Env caps for API-driven scrapes (single or bulk)."""
    keys = (
        "SCRAPE_MAX_POSTS",
        "SCRAPE_ENRICH_MAX",
        "SCRAPE_MAX_RETRIES",
        "SCRAPE_USE_BROWSER",
        "SCRAPE_BROWSER_ON_PARTIAL",
        "SCRAPE_STRICT",
    )
    previous = {k: os.environ.get(k) for k in keys}

    max_posts = (os.getenv("SCRAPE_INLINE_MAX_POSTS") or "0").strip() or "0"
    enrich_max = (os.getenv("SCRAPE_INLINE_ENRICH_MAX") or "12").strip() or "12"
    retries = (os.getenv("SCRAPE_INLINE_MAX_RETRIES") or "1").strip() or "1"
    os.environ["SCRAPE_MAX_POSTS"] = max_posts
    os.environ["SCRAPE_ENRICH_MAX"] = enrich_max
    os.environ["SCRAPE_MAX_RETRIES"] = retries

    from instascope_scraper.proxy_pool import pool_size as _proxy_pool_size

    if "SCRAPE_INLINE_USE_BROWSER" in os.environ:
        os.environ["SCRAPE_USE_BROWSER"] = (
            os.environ.get("SCRAPE_INLINE_USE_BROWSER") or "0"
        ).strip() or "0"
    else:
        os.environ["SCRAPE_USE_BROWSER"] = "1" if _proxy_pool_size() > 0 else "0"
    os.environ["SCRAPE_BROWSER_ON_PARTIAL"] = (
        os.getenv("SCRAPE_INLINE_BROWSER_ON_PARTIAL") or "0"
    ).strip() or "0"
    os.environ["SCRAPE_STRICT"] = (os.getenv("SCRAPE_INLINE_STRICT") or "0").strip() or "0"
    prev_page_delay = os.environ.get("SCRAPE_PAGE_DELAY_SECONDS")
    if prev_page_delay is None:
        os.environ["SCRAPE_PAGE_DELAY_SECONDS"] = (
            os.getenv("SCRAPE_INLINE_PAGE_DELAY_SECONDS") or "0.35"
        ).strip() or "0.35"
    try:
        yield
    finally:
        for k, v in previous.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        if prev_page_delay is None:
            os.environ.pop("SCRAPE_PAGE_DELAY_SECONDS", None)
        else:
            os.environ["SCRAPE_PAGE_DELAY_SECONDS"] = prev_page_delay


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


async def _set_progress(profile: Profile, job: Job, payload: dict[str, Any]) -> None:
    profile.scrape_progress = payload
    profile.updated_at = datetime.utcnow()
    await profile.save()
    meta = dict(job.meta or {})
    meta.update(payload)
    job.meta = meta
    job.updated_at = datetime.utcnow()
    await job.save()


async def run_profile_scrape(
    profile: Profile,
    *,
    source: ScrapeSource = "single",
) -> Job:
    """Run one live Instagram scrape and persist results.

    Used by both the single-profile runner and the bulk queue worker.
    """
    try:
        from instascope_shared.services.app_config import apply_proxy_config_to_env

        await apply_proxy_config_to_env()
    except Exception:
        pass

    settings = get_settings()
    job = Job(
        user_id=profile.user_id,
        profile_id=str(profile.id),
        job_type=JobType.SCRAPE_PROFILE,
        status=JobStatus.RUNNING,
        priority=1,
        started_at=datetime.utcnow(),
        attempts=1,
        meta={"phase": "starting", "source": source},
    )
    await job.insert()

    proxy = next_proxy() if pool_size() > 0 else parse_proxy_url(settings.scrape_proxy_url)
    last_progress = progress_payload(
        scraped=0,
        total=int(profile.posts_count or 0),
        phase="starting",
        source=source,
    )
    await _set_progress(profile, job, last_progress)

    async def on_progress(info: dict[str, Any]) -> None:
        nonlocal last_progress
        scraped = int(info.get("scraped_posts") or info.get("scraped") or 0)
        total = int(info.get("total_posts") or info.get("total") or 0)
        phase = str(info.get("phase") or "scraping")
        last_progress = progress_payload(
            scraped=scraped, total=total, phase=phase, active=True, source=source
        )
        await _set_progress(profile, job, last_progress)

    async def _heartbeat() -> None:
        while True:
            await asyncio.sleep(8)
            payload = dict(last_progress)
            payload["updated_at"] = datetime.utcnow().isoformat() + "Z"
            payload["active"] = True
            payload["source"] = source
            try:
                await _set_progress(profile, job, payload)
            except Exception:  # noqa: BLE001
                return

    with _scrape_caps():
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
                    ),
                    timeout=_job_timeout_seconds(),
                )
            except asyncio.TimeoutError as exc:
                raise ScrapeError(
                    f"Scrape timed out after {int(_job_timeout_seconds())}s "
                    f"(Instagram/proxy too slow). Try Refresh again."
                ) from exc

            await _set_progress(
                profile,
                job,
                progress_payload(
                    scraped=len(result.posts),
                    total=int(result.posts_count or len(result.posts)),
                    phase="saving",
                    active=True,
                    source=source,
                ),
            )
            await apply_scrape_result(job=job, profile=profile, result=result.to_dict())
            profile.scrape_progress = progress_payload(
                scraped=len(result.posts),
                total=int(result.posts_count or len(result.posts)),
                phase="done",
                active=False,
                source=source,
            )
            await profile.save()
        except ScrapeError as exc:
            await mark_scrape_failed(job, profile, str(exc), unavailable=exc.unavailable)
            profile.scrape_progress = progress_payload(
                scraped=int(last_progress.get("scraped_posts") or 0),
                total=int(last_progress.get("total_posts") or profile.posts_count or 0),
                phase="failed",
                active=False,
                source=source,
            )
            await profile.save()
        except Exception as exc:  # noqa: BLE001
            await mark_scrape_failed(job, profile, str(exc))
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
