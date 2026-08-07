"""Celery app + Beat schedule.

Daily fan-out scrapes every ACTIVE profile at 08:00 Asia/Kolkata (IST) by default.
Override with DAILY_SCRAPE_HOUR_IST / DAILY_SCRAPE_MINUTE_IST / CELERY_TIMEZONE.
"""

from celery import Celery
from celery.schedules import crontab

from instascope_shared.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "instascope",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["tasks.scrape_profile", "tasks.fanout_daily", "tasks.retry_failed"],
)

_tz = (settings.celery_timezone or "Asia/Kolkata").strip() or "Asia/Kolkata"
_hour = max(0, min(23, int(settings.daily_scrape_hour_ist)))
_minute = max(0, min(59, int(settings.daily_scrape_minute_ist)))

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=_tz,
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        # Every morning IST — enqueue a full programme-window scrape for each active account.
        "daily-scrape-all-profiles": {
            "task": "tasks.fanout_daily",
            "schedule": crontab(hour=_hour, minute=_minute),
        },
        "retry-failed": {
            "task": "tasks.retry_failed",
            "schedule": crontab(minute="*/30"),
        },
    },
)
