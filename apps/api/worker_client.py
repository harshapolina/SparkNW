"""Optional Celery dispatch used by API (fails soft if broker down)."""

from instascope_shared.core.config import get_settings


def dispatch_scrape_job(job_id: str, profile_id: str) -> str | None:
    try:
        from celery import Celery

        settings = get_settings()
        c = Celery("instascope", broker=settings.redis_url, backend=settings.redis_url)
        result = c.send_task("tasks.scrape_profile", args=[job_id, profile_id])
        return result.id
    except Exception:
        return None
