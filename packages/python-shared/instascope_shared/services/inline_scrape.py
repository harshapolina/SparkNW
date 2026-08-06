"""Compatibility shim — scrape logic lives in scrape_core.

Prefer:
  from instascope_shared.services.scrape_core import run_profile_scrape
"""

from __future__ import annotations

from instascope_shared.models import Job, Profile
from instascope_shared.services.scrape_core import run_profile_scrape


async def scrape_profile_inline(profile: Profile) -> Job:
    """Deprecated alias for run_profile_scrape(source='single')."""
    return await run_profile_scrape(profile, source="single")
