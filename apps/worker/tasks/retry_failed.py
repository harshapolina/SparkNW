"""Re-queue failed Instagram scrape jobs under max attempts.

Never retries YouTube sync/connect jobs — those must not run through the
Instagram scrape pipeline (that was overwriting YouTube failures with proxy errors).
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from celery_app import celery_app
from instascope_shared.db.mongodb import close_db, connect_db
from instascope_shared.models import Job, JobStatus, JobType
from tasks.scrape_profile import scrape_profile_task


async def _retry() -> dict:
    await connect_db()
    try:
        failed = await Job.find(
            Job.status == JobStatus.FAILED,
            Job.job_type == JobType.SCRAPE_PROFILE,
        ).to_list()
        retried = 0
        skipped_other = 0
        for job in failed:
            if job.attempts >= job.max_attempts or not job.profile_id:
                continue
            # Belt-and-suspenders if job_type was stored oddly
            jt = job.job_type.value if hasattr(job.job_type, "value") else str(job.job_type or "")
            if jt != JobType.SCRAPE_PROFILE.value:
                skipped_other += 1
                continue
            job.status = JobStatus.RETRYING
            job.updated_at = datetime.utcnow()
            await job.save()
            scrape_profile_task.delay(str(job.id), job.profile_id)
            retried += 1
        return {"retried": retried, "skipped_other_types": skipped_other}
    finally:
        await close_db()


@celery_app.task(name="tasks.retry_failed")
def retry_failed():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_retry())
    finally:
        loop.close()
