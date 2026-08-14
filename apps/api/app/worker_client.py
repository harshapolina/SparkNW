"""Optional Celery dispatch used by API (fails soft if broker down)."""

from instascope_shared.core.config import get_settings


def _celery():
    from celery import Celery

    settings = get_settings()
    return Celery("instascope", broker=settings.redis_url, backend=settings.redis_url)


def dispatch_scrape_job(job_id: str, profile_id: str) -> str | None:
    try:
        result = _celery().send_task("tasks.scrape_profile", args=[job_id, profile_id])
        return result.id
    except Exception:
        return None


def dispatch_youtube_sync_job(job_id: str, profile_id: str, *, countdown: int = 0) -> str | None:
    try:
        result = _celery().send_task(
            "tasks.sync_youtube",
            args=[job_id, profile_id],
            countdown=max(0, int(countdown)),
        )
        return result.id
    except Exception:
        return None


def dispatch_youtube_connect_job(
    job_id: str,
    profile_id: str,
    url: str,
    *,
    countdown: int = 0,
) -> str | None:
    try:
        result = _celery().send_task(
            "tasks.connect_youtube",
            args=[job_id, profile_id, url],
            countdown=max(0, int(countdown)),
        )
        return result.id
    except Exception:
        return None


def dispatch_fanout_youtube() -> str | None:
    """Trigger Celery fan-out for all connected YouTube channels (respects toggle)."""
    try:
        result = _celery().send_task("tasks.fanout_youtube")
        return result.id
    except Exception:
        return None
