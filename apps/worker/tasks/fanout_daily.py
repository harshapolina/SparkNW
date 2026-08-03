"""Daily fan-out: enqueue one scrape job per active profile."""

from __future__ import annotations

import asyncio
from datetime import datetime

from celery_app import celery_app
from instascope_shared.db.mongodb import close_db, connect_db
from instascope_shared.models import Job, JobStatus, JobType, Profile, ProfileStatus
from tasks.scrape_profile import scrape_profile_task


async def _fanout() -> dict:
    await connect_db()
    try:
        profiles = await Profile.find(Profile.status == ProfileStatus.ACTIVE).to_list()
        enqueued = 0
        for profile in profiles:
            job = Job(
                user_id=profile.user_id,
                profile_id=str(profile.id),
                job_type=JobType.SCRAPE_PROFILE,
                status=JobStatus.PENDING,
                priority=5,
                scheduled_at=datetime.utcnow(),
            )
            await job.insert()
            scrape_profile_task.delay(str(job.id), str(profile.id))
            enqueued += 1
        return {"enqueued": enqueued}
    finally:
        await close_db()


@celery_app.task(name="tasks.fanout_daily")
def fanout_daily():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_fanout())
    finally:
        loop.close()
