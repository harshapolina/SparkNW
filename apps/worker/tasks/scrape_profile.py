"""One profile scrape per Celery task."""

from __future__ import annotations

import asyncio
from datetime import datetime

from celery_app import celery_app
from instascope_shared.core.config import get_settings
from instascope_shared.db.mongodb import close_db, connect_db
from instascope_shared.models import Job, JobStatus, Profile, ProfileStatus
from instascope_shared.services.scrape_pipeline import apply_scrape_result, mark_scrape_failed
from instascope_scraper.profile import ScrapeError, scrape_profile
from instascope_scraper.types import parse_proxy_url


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


async def _scrape(job_id: str, profile_id: str) -> dict:
    await connect_db()
    try:
        settings = get_settings()
        job = await Job.get(job_id)
        profile = await Profile.get(profile_id)
        if not job or not profile:
            return {"ok": False, "error": "missing job/profile"}

        if profile.status == ProfileStatus.PAUSED:
            job.status = JobStatus.CANCELLED
            job.finished_at = datetime.utcnow()
            await job.save()
            return {"ok": False, "error": "paused"}

        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        job.attempts += 1
        await job.save()

        proxy = parse_proxy_url(settings.scrape_proxy_url)

        try:
            result = await scrape_profile(
                profile.username,
                headless=settings.scrape_headless,
                proxy=proxy,
                delay_seconds=settings.scrape_delay_seconds,
            )
            await apply_scrape_result(job=job, profile=profile, result=result.to_dict())
            return {"ok": True, "followers": result.followers}
        except ScrapeError as exc:
            await mark_scrape_failed(job, profile, str(exc), unavailable=exc.unavailable)
            return {"ok": False, "error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            await mark_scrape_failed(job, profile, str(exc))
            raise
    finally:
        await close_db()


@celery_app.task(name="tasks.scrape_profile", bind=True, max_retries=3, default_retry_delay=60)
def scrape_profile_task(self, job_id: str, profile_id: str):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_scrape(job_id, profile_id))
        finally:
            loop.close()
    except Exception as exc:  # noqa: BLE001
        raise self.retry(exc=exc)
