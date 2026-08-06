"""Compatibility shim — prefer scrape_core.run_profile_scrape."""

from __future__ import annotations

from instascope_shared.models import Job, Profile
from instascope_shared.services.scrape_core import run_profile_scrape


async def scrape_profile_inline(profile: Profile) -> Job:
    return await run_profile_scrape(profile, source="single")
