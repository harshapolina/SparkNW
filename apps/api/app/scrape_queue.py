"""Deprecated shim — use scrape_bulk / scrape_single.

Kept so older imports (`from app.scrape_queue import …`) keep working.
"""

from app.scrape_bulk import (  # noqa: F401
    clear_stale_scrape_progress,
    deep_pending_count,
    ensure_bulk_worker,
    enqueue_bulk_profile_ids,
    enqueue_deep_profile_ids,
    enqueue_profile_ids,
    mark_profiles_queued,
    pending_count,
    resume_incomplete_bulk_scrapes,
    resume_incomplete_scrapes,
    running_mode,
    running_profile_id,
    sample_pending_count,
)
