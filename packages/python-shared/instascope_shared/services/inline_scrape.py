"""Inline live scrape used by API add/refresh endpoints."""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator

from instascope_shared.core.config import get_settings
from instascope_shared.models import Job, JobStatus, JobType, Profile
from instascope_shared.services.scrape_pipeline import apply_scrape_result, mark_scrape_failed
from instascope_scraper.profile import ScrapeError, scrape_profile
from instascope_scraper.types import parse_proxy_url


@contextmanager
def _inline_scrape_caps() -> Iterator[None]:
    """Inline scrape env for API Add/Refresh/bulk.

    - Posts: default ALL (SCRAPE_INLINE_MAX_POSTS=0) — full public timeline.
    - Enrich: keep capped so per-post page opens don't make scrapes hang for hours.
    """
    keys = ("SCRAPE_MAX_POSTS", "SCRAPE_ENRICH_MAX")
    previous = {k: os.environ.get(k) for k in keys}

    max_posts = (os.getenv("SCRAPE_INLINE_MAX_POSTS") or "0").strip() or "0"
    enrich_max = (os.getenv("SCRAPE_INLINE_ENRICH_MAX") or "12").strip() or "12"
    os.environ["SCRAPE_MAX_POSTS"] = max_posts
    os.environ["SCRAPE_ENRICH_MAX"] = enrich_max
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


def _progress_payload(
    *,
    scraped: int,
    total: int,
    phase: str,
    active: bool = True,
) -> dict[str, Any]:
    total_n = max(0, int(total or 0))
    scraped_n = max(0, int(scraped or 0))
    if total_n > 0:
        percent = min(100, int(round(100 * scraped_n / total_n)))
    else:
        percent = 0 if active else 100
    left = max(0, total_n - scraped_n) if total_n > 0 else 0
    return {
        "active": active,
        "phase": phase,
        "scraped_posts": scraped_n,
        "total_posts": total_n,
        "posts_left": left,
        "percent": percent,
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }


async def _set_progress(profile: Profile, job: Job, payload: dict[str, Any]) -> None:
    profile.scrape_progress = payload
    profile.updated_at = datetime.utcnow()
    await profile.save()
    meta = dict(job.meta or {})
    meta.update(payload)
    job.meta = meta
    job.updated_at = datetime.utcnow()
    await job.save()


async def scrape_profile_inline(profile: Profile) -> Job:
    settings = get_settings()
    job = Job(
        user_id=profile.user_id,
        profile_id=str(profile.id),
        job_type=JobType.SCRAPE_PROFILE,
        status=JobStatus.RUNNING,
        priority=1,
        started_at=datetime.utcnow(),
        attempts=1,
        meta={"phase": "starting"},
    )
    await job.insert()

    proxy = parse_proxy_url(settings.scrape_proxy_url)
    await _set_progress(
        profile,
        job,
        _progress_payload(scraped=0, total=int(profile.posts_count or 0), phase="starting"),
    )

    async def on_progress(info: dict[str, Any]) -> None:
        scraped = int(info.get("scraped_posts") or info.get("scraped") or 0)
        total = int(info.get("total_posts") or info.get("total") or 0)
        phase = str(info.get("phase") or "scraping")
        await _set_progress(
            profile,
            job,
            _progress_payload(scraped=scraped, total=total, phase=phase, active=True),
        )

    with _inline_scrape_caps():
        try:
            result = await scrape_profile(
                profile.username,
                headless=settings.scrape_headless,
                proxy=proxy,
                delay_seconds=settings.scrape_delay_seconds,
                live=True,
                on_progress=on_progress,
            )
            await _set_progress(
                profile,
                job,
                _progress_payload(
                    scraped=len(result.posts),
                    total=int(result.posts_count or len(result.posts)),
                    phase="saving",
                    active=True,
                ),
            )
            await apply_scrape_result(job=job, profile=profile, result=result.to_dict())
            profile.scrape_progress = _progress_payload(
                scraped=len(result.posts),
                total=int(result.posts_count or len(result.posts)),
                phase="done",
                active=False,
            )
            await profile.save()
        except ScrapeError as exc:
            await mark_scrape_failed(job, profile, str(exc), unavailable=exc.unavailable)
            profile.scrape_progress = _progress_payload(
                scraped=0, total=int(profile.posts_count or 0), phase="failed", active=False
            )
            await profile.save()
        except Exception as exc:  # noqa: BLE001
            await mark_scrape_failed(job, profile, str(exc))
            profile.scrape_progress = _progress_payload(
                scraped=0, total=int(profile.posts_count or 0), phase="failed", active=False
            )
            await profile.save()
    return job
