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
    """Speed caps for API-path scrapes so large accounts finish and save data.

    Server .env often has SCRAPE_MAX_POSTS=0 (all) + SCRAPE_ENRICH_MAX=0 (all),
    which makes 100k+ accounts hang for 10+ minutes and then timeout with nothing saved.
    """
    keys = ("SCRAPE_MAX_POSTS", "SCRAPE_ENRICH_MAX", "SCRAPE_STRICT")
    previous = {k: os.environ.get(k) for k in keys}

    # Default first-pass: recent ~48 posts, light enrich, allow capped completeness.
    max_posts = (os.getenv("SCRAPE_INLINE_MAX_POSTS") or "48").strip() or "48"
    enrich_max = (os.getenv("SCRAPE_INLINE_ENRICH_MAX") or "12").strip() or "12"
    os.environ["SCRAPE_MAX_POSTS"] = max_posts
    os.environ["SCRAPE_ENRICH_MAX"] = enrich_max
    # Completeness is judged against the cap in scrape_pipeline when MAX_POSTS > 0.
    os.environ.setdefault("SCRAPE_STRICT", previous.get("SCRAPE_STRICT") or "1")
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
