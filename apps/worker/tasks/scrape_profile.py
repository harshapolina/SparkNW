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
        except ScrapeError as exc:
            await mark_scrape_failed(job, profile, str(exc), unavailable=exc.unavailable)
            return {"ok": False, "error": str(exc), "unavailable": exc.unavailable}
        except Exception as exc:  # noqa: BLE001
            await mark_scrape_failed(job, profile, str(exc))
            return {"ok": False, "error": str(exc), "retryable": True}

        try:
            await apply_scrape_result(job=job, profile=profile, result=result.to_dict())
            return {"ok": True, "followers": result.followers}
        except Exception as exc:  # noqa: BLE001
            from instascope_shared.services.scrape_pipeline import is_soft_scrape_failure

            msg = str(exc)
            if is_soft_scrape_failure(exc):
                # Keep existing DB data intact — never wipe to zeros
                if profile.status != ProfileStatus.PAUSED:
                    profile.status = ProfileStatus.ACTIVE
                profile.last_error = None
                profile.updated_at = datetime.utcnow()
                await profile.save()
                job.status = JobStatus.FAILED
                job.error_message = msg[:280]
                job.finished_at = datetime.utcnow()
                await job.save()
                return {"ok": False, "error": msg, "preserved": True}
            await mark_scrape_failed(job, profile, f"Save failed after scrape: {exc}")
            return {"ok": False, "error": msg}
    finally:
        await close_db()


@celery_app.task(name="tasks.scrape_profile", bind=True, max_retries=2, default_retry_delay=90)
def scrape_profile_task(self, job_id: str, profile_id: str):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(_scrape(job_id, profile_id))
        if isinstance(result, dict) and result.get("retryable") and not result.get("unavailable"):
            raise self.retry(exc=RuntimeError(result.get("error") or "transient scrape error"))
        return result
    finally:
        loop.close()
