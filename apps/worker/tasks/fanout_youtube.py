"""Daily YouTube fan-out — enqueue one sync job per connected channel.

Independent of Instagram daily-scrape toggle. Gated by app_config
`daily_youtube_sync.enabled`. One channel failure must not stop others
(each sync runs as its own Celery task).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from celery_app import celery_app
from instascope_shared.core.config import get_settings
from instascope_shared.db.mongodb import close_db, connect_db
from instascope_shared.models import Job, JobStatus, JobType, YouTubeChannel
from tasks.sync_youtube import sync_youtube_task

logger = logging.getLogger("instascope.worker.fanout_youtube")


async def _fanout() -> dict:
    await connect_db()
    try:
        from instascope_shared.services.app_config import is_daily_youtube_sync_enabled

        if not await is_daily_youtube_sync_enabled():
            summary = {
                "enqueued": 0,
                "skipped": True,
                "reason": "daily_youtube_sync_disabled",
            }
            logger.info("YouTube daily fanout skipped — admin toggle is off")
            return summary

        settings = get_settings()
        stagger = max(0.0, float(settings.daily_youtube_sync_stagger_seconds or 0))
        channels = await YouTubeChannel.find(YouTubeChannel.connected == True).to_list()  # noqa: E712

        enqueued = 0
        skipped_pending = 0
        for i, ch in enumerate(channels):
            pid = ch.profile_id
            existing = await Job.find_one(
                Job.profile_id == pid,
                Job.job_type == JobType.SYNC_YOUTUBE,
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
                user_id=ch.user_id,
                profile_id=pid,
                job_type=JobType.SYNC_YOUTUBE,
                status=JobStatus.PENDING,
                priority=5,
                scheduled_at=datetime.utcnow(),
                meta={"channel_id": ch.channel_id},
            )
            await job.insert()
            countdown = int(i * stagger) if stagger > 0 else 0
            sync_youtube_task.apply_async(
                args=(str(job.id), pid),
                countdown=countdown,
            )
            enqueued += 1

        summary = {
            "enqueued": enqueued,
            "skipped_pending": skipped_pending,
            "connected_total": len(channels),
            "stagger_seconds": stagger,
        }
        logger.info("YouTube daily fanout done %s", summary)
        return summary
    finally:
        await close_db()


@celery_app.task(name="tasks.fanout_youtube")
def fanout_youtube():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_fanout())
    finally:
        loop.close()
