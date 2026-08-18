"""Rebuild the public Top 10 snapshot in the background (Framer embed)."""

from __future__ import annotations

import asyncio
import logging

from celery_app import celery_app
from instascope_shared.db.mongodb import close_db, connect_db
from instascope_shared.models import DEFAULT_ORG_ID

logger = logging.getLogger("instascope.worker.top10")


async def _refresh(org_id: str | None) -> dict:
    await connect_db()
    try:
        from instascope_shared.services.spark import refresh_top10_snapshot

        return await refresh_top10_snapshot(org_id or DEFAULT_ORG_ID, force=True)
    finally:
        await close_db()


@celery_app.task(name="tasks.refresh_top10", expires=90)
def refresh_top10(org_id: str | None = None):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        payload = loop.run_until_complete(_refresh(org_id))
        logger.info(
            "top10 snapshot refreshed org=%s items=%s total=%s",
            org_id or DEFAULT_ORG_ID,
            len(payload.get("items") or []),
            payload.get("total_creators"),
        )
        return {
            "ok": True,
            "total_creators": payload.get("total_creators"),
            "items": len(payload.get("items") or []),
        }
    finally:
        loop.close()
