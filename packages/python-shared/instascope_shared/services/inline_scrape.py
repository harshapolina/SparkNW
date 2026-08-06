"""Inline live scrape used by API add/refresh endpoints."""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator

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

    # 0 = all posts (matches server SCRAPE_MAX_POSTS=0 intent).
    max_posts = (os.getenv("SCRAPE_INLINE_MAX_POSTS") or "0").strip() or "0"
    enrich_max = (os.getenv("SCRAPE_INLINE_ENRICH_MAX") or "24").strip() or "24"
    os.environ["SCRAPE_MAX_POSTS"] = max_posts
    os.environ["SCRAPE_ENRICH_MAX"] = enrich_max
    try:
        yield
    finally:
        for k, v in previous.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


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
    )
    await job.insert()

    proxy = parse_proxy_url(settings.scrape_proxy_url)

    with _inline_scrape_caps():
        try:
            result = await scrape_profile(
                profile.username,
                headless=settings.scrape_headless,
                proxy=proxy,
                delay_seconds=settings.scrape_delay_seconds,
                live=True,
            )
            await apply_scrape_result(job=job, profile=profile, result=result.to_dict())
        except ScrapeError as exc:
            await mark_scrape_failed(job, profile, str(exc), unavailable=exc.unavailable)
        except Exception as exc:  # noqa: BLE001
            await mark_scrape_failed(job, profile, str(exc))
    return job
