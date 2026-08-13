"""Per-profile YouTube connect+sync Celery task (used by bulk import).

Resolves URL/@handle once, stores channel_id, then syncs programme-window videos.
Isolated failures — one bad handle must not stop the queue.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from celery_app import celery_app
from instascope_shared.db.mongodb import close_db, connect_db
from instascope_shared.models import Job, JobStatus, Profile
from instascope_shared.services.youtube_errors import YouTubeError
from instascope_shared.services.youtube_sync import connect_youtube_channel

logger = logging.getLogger("instascope.worker.youtube_connect")


async def _connect(job_id: str, profile_id: str, url: str) -> dict:
    await connect_db()
    try:
        job = await Job.get(job_id)
        if job:
            job.status = JobStatus.RUNNING
            job.started_at = datetime.utcnow()
            job.attempts = int(job.attempts or 0) + 1
            await job.save()

        profile = await Profile.get(profile_id)
        if not profile:
            if job:
                job.status = JobStatus.FAILED
                job.error_message = "Profile not found"
                job.finished_at = datetime.utcnow()
                await job.save()
            return {"ok": False, "profile_id": profile_id, "error": "profile_not_found"}

        try:
            result = await connect_youtube_channel(
                profile,
                url,
                sync_videos=True,
                max_videos=0,
            )
            # Mark roster status when student blob exists
            student = dict(getattr(profile, "student", None) or {})
            if student:
                student["youtube_status"] = "Connected"
                profile.student = student
                profile.updated_at = datetime.utcnow()
                await profile.save()
            if job:
                job.status = JobStatus.SUCCESS
                job.error_message = None
                job.finished_at = datetime.utcnow()
                job.meta = {**(job.meta or {}), "youtube": result, "url": url[:200]}
                await job.save()
            return {"ok": True, "profile_id": profile_id, **result}
        except YouTubeError as exc:
            if job:
                job.status = JobStatus.FAILED
                job.error_message = str(exc)[:280]
                job.finished_at = datetime.utcnow()
                await job.save()
            logger.warning(
                "YouTube connect failed profile=%s url=%s err=%s",
                profile_id,
                url[:80],
                exc,
            )
            return {"ok": False, "profile_id": profile_id, "error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            if job:
                job.status = JobStatus.FAILED
                job.error_message = str(exc)[:280]
                job.finished_at = datetime.utcnow()
                await job.save()
            logger.exception("YouTube connect unexpected error profile=%s", profile_id)
            return {"ok": False, "profile_id": profile_id, "error": str(exc)}
    finally:
        await close_db()


@celery_app.task(name="tasks.connect_youtube", bind=True, max_retries=0)
def connect_youtube_task(self, job_id: str, profile_id: str, url: str):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_connect(job_id, profile_id, url))
    finally:
        loop.close()
