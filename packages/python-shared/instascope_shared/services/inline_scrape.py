"""Inline live scrape used by API add/refresh endpoints."""

from __future__ import annotations

from datetime import datetime

from instascope_shared.core.config import get_settings
from instascope_shared.models import Job, JobStatus, JobType, Profile
from instascope_shared.services.scrape_pipeline import apply_scrape_result, mark_scrape_failed
from instascope_scraper.profile import ScrapeError, scrape_profile
from instascope_scraper.types import ProxyConfig


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

    proxy = None
    if settings.scrape_proxy_url:
        proxy = ProxyConfig(server=settings.scrape_proxy_url)

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
