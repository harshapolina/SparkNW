"""Daily YouTube fan-out — enqueue one sync job per connected channel.

Also auto-connects roster rows that have a YouTube link/@handle but are not
linked yet (so bulk-imported creators get picked up on the morning run).

Independent of Instagram daily-scrape toggle. Gated by app_config
`daily_youtube_sync.enabled`. One channel failure must not stop others.
"""

from __future__ import annotations

import asyncio
import logging

from celery_app import celery_app
from instascope_shared.db.mongodb import close_db, connect_db
from tasks.connect_youtube import connect_youtube_task
from tasks.sync_youtube import sync_youtube_task

logger = logging.getLogger("instascope.worker.fanout_youtube")


async def _enqueue_missing_roster_connects() -> dict:
    """Connect profiles that still have roster YouTube fields but no channel link."""
    from instascope_shared.models import Profile
    from instascope_shared.services.youtube_jobs import (
        enqueue_youtube_connects,
        youtube_ref_from_student,
    )

    # Limit scan — prefer not-yet-connected profiles with student blob
    candidates = await Profile.find(
        {
            "youtube_connected": {"$ne": True},
            "student": {"$exists": True},
        }
    ).limit(2000).to_list()

    items: list[tuple[str, str, str]] = []
    for p in candidates:
        ref = youtube_ref_from_student(dict(getattr(p, "student", None) or {}))
        if not ref:
            continue
        items.append((str(p.id), str(p.user_id), ref))

    if not items:
        return {"enqueued": 0, "jobs": []}

    summary = await enqueue_youtube_connects(items, source="daily_fanout_connect")
    for job in summary.get("jobs") or []:
        connect_youtube_task.apply_async(
            args=(job["job_id"], job["profile_id"], job["url"]),
            countdown=int(job.get("countdown") or 0),
        )
    return summary


async def _fanout() -> dict:
    await connect_db()
    try:
        from instascope_shared.services.app_config import is_daily_youtube_sync_enabled
        from instascope_shared.services.youtube_jobs import enqueue_connected_youtube_syncs

        if not await is_daily_youtube_sync_enabled():
            summary = {
                "enqueued": 0,
                "skipped": True,
                "reason": "daily_youtube_sync_disabled",
            }
            logger.info("YouTube daily fanout skipped — admin toggle is off")
            return summary

        connect_summary = await _enqueue_missing_roster_connects()
        result = await enqueue_connected_youtube_syncs()
        for job in result.get("jobs") or []:
            sync_youtube_task.apply_async(
                args=(job["job_id"], job["profile_id"]),
                countdown=int(job.get("countdown") or 0),
            )
        out = {
            "enqueued": result.get("enqueued"),
            "skipped_pending": result.get("skipped_pending"),
            "connected_total": result.get("connected_total"),
            "connect_enqueued": connect_summary.get("enqueued"),
        }
        logger.info("YouTube daily fanout done %s", out)
        return out
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
