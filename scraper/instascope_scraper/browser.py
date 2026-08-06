"""Playwright browser factory with proxy + retry-friendly context."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from playwright.async_api import Browser, Playwright, async_playwright

from instascope_scraper.types import ProxyConfig


def _launch_timeout_seconds() -> float:
    raw = (os.getenv("SCRAPE_BROWSER_LAUNCH_TIMEOUT_SECONDS") or "60").strip()
    try:
        return max(15.0, float(raw))
    except ValueError:
        return 60.0


@asynccontextmanager
async def browser_session(
    *,
    headless: bool = True,
    proxy: Optional[ProxyConfig] = None,
) -> AsyncIterator[Browser]:
    playwright: Playwright = await asyncio.wait_for(async_playwright().start(), timeout=30)
    launch_kwargs: dict = {"headless": headless}
    if proxy:
        launch_kwargs["proxy"] = {
            "server": proxy.server,
            **({"username": proxy.username} if proxy.username else {}),
            **({"password": proxy.password} if proxy.password else {}),
        }
    try:
        browser = await asyncio.wait_for(
            playwright.chromium.launch(**launch_kwargs),
            timeout=_launch_timeout_seconds(),
        )
    except Exception:
        await playwright.stop()
        raise
    try:
        yield browser
    finally:
        try:
            await asyncio.wait_for(browser.close(), timeout=15)
        except Exception:
            pass
        try:
            await asyncio.wait_for(playwright.stop(), timeout=15)
        except Exception:
            pass
