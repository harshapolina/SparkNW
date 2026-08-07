"""Daily fan-out: enqueue one scrape job per active public profile.

Runs from Celery Beat at 08:00 IST (configurable). Workers then scrape each
account for updated followers + programme-window posts/metrics.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from celery_app import celery_app
from instascope_shared.core.config import get_settings
from instascope_shared.db.mongodb import close_db, connect_db
from instascope_shared.models import Job, JobStatus, JobType, Profile, ProfileStatus
from tasks.scrape_profile import scrape_profile_task

logger = logging.getLogger("instascope.worker.fanout")


async def _fanout() -> dict:
    await connect_db()
    try:
        settings = get_settings()
        stagger = max(0.0, float(settings.daily_scrape_stagger_seconds or 0))
        profiles = await Profile.find(Profile.status == ProfileStatus.ACTIVE).to_list()

        enqueued = 0
        skipped_private = 0
        skipped_pending = 0

        for i, profile in enumerate(profiles):
            if bool(getattr(profile, "is_private", False)):
                skipped_private += 1
                continue

            pid = str(profile.id)
            # Avoid stacking duplicate daily jobs if Beat fires twice or a prior
            # run is still queued.
            existing = await Job.find_one(
                Job.profile_id == pid,
                Job.job_type == JobType.SCRAPE_PROFILE,
                {
                    "status": {
                        "$in": [
                            JobStatus.PENDING,
                            JobStatus.RUNNING,
                            JobStatus.RETRYING,
                        ]
                    }
                },
            )
            if existing is not None:
                skipped_pending += 1
                continue

            job = Job(
                user_id=profile.user_id,
                profile_id=pid,
                job_type=JobType.SCRAPE_PROFILE,
                status=JobStatus.PENDING,
                priority=5,
                scheduled_at=datetime.utcnow(),
            )
            await job.insert()
            countdown = int(i * stagger) if stagger > 0 else 0
            scrape_profile_task.apply_async(
                args=(str(job.id), pid),
                countdown=countdown,
            )
            enqueued += 1
            logger.info(
                "daily scrape queued @%s job=%s countdown=%ss",
                profile.username,
                job.id,
                countdown,
            )

        summary = {
            "enqueued": enqueued,
            "skipped_private": skipped_private,
            "skipped_pending": skipped_pending,
            "active_total": len(profiles),
            "stagger_seconds": stagger,
        }
        logger.info("daily fanout done %s", summary)
        return summary
    finally:
        await close_db()


@celery_app.task(name="tasks.fanout_daily")
def fanout_daily():
    """Beat entrypoint — scrape every active account for fresh Insights data."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_fanout())
    finally:
        loop.close()
