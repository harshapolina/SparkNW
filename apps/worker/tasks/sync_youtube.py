"""Per-profile YouTube sync Celery task (isolated failures)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from celery_app import celery_app
from instascope_shared.db.mongodb import close_db, connect_db
from instascope_shared.models import Job, JobStatus
from instascope_shared.services.youtube_errors import YouTubeError
from instascope_shared.services.youtube_sync import sync_youtube_channel

logger = logging.getLogger("instascope.worker.youtube")


async def _sync(job_id: str, profile_id: str) -> dict:
    await connect_db()
    try:
        job = await Job.get(job_id)
        if job:
            job.status = JobStatus.RUNNING
            job.started_at = datetime.utcnow()
            job.attempts = int(job.attempts or 0) + 1
            await job.save()
        try:
            result = await sync_youtube_channel(profile_id)
            if job:
                job.status = JobStatus.SUCCESS
                job.error_message = None
                job.finished_at = datetime.utcnow()
                job.meta = {**(job.meta or {}), "youtube": result}
                await job.save()
            return result
        except YouTubeError as exc:
            if job:
                job.status = JobStatus.FAILED
                job.error_message = str(exc)[:280]
                job.finished_at = datetime.utcnow()
                await job.save()
            logger.warning("YouTube sync task failed profile=%s err=%s", profile_id, exc)
            return {"ok": False, "profile_id": profile_id, "error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            if job:
                job.status = JobStatus.FAILED
                job.error_message = str(exc)[:280]
                job.finished_at = datetime.utcnow()
                await job.save()
            logger.exception("YouTube sync unexpected error profile=%s", profile_id)
            return {"ok": False, "profile_id": profile_id, "error": str(exc)}
    finally:
        await close_db()


@celery_app.task(name="tasks.sync_youtube", bind=True, max_retries=0)
def sync_youtube_task(self, job_id: str, profile_id: str):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_sync(job_id, profile_id))
    finally:
        loop.close()
