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

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "daily-fanout": {
            "task": "tasks.fanout_daily",
            "schedule": crontab(hour=settings.daily_scrape_hour_utc, minute=0),
        },
        "retry-failed": {
            "task": "tasks.retry_failed",
            "schedule": crontab(minute="*/30"),
        },
    },
)
