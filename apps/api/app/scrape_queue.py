"""Deprecated shim — use scrape_bulk / scrape_single.

Kept so older imports (`from app.scrape_queue import …`) keep working.
"""

from app.scrape_bulk import (  # noqa: F401
    clear_stale_scrape_progress,
    ensure_bulk_worker,
    enqueue_bulk_profile_ids,
    enqueue_profile_ids,
    mark_profiles_queued,
    pending_count,
    resume_incomplete_bulk_scrapes,
    resume_incomplete_scrapes,
    running_profile_id,
)
