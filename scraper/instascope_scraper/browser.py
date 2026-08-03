"""Playwright browser factory with proxy + retry-friendly context."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from playwright.async_api import Browser, Playwright, async_playwright

from instascope_scraper.types import ProxyConfig


@asynccontextmanager
async def browser_session(
    *,
    headless: bool = True,
    proxy: Optional[ProxyConfig] = None,
) -> AsyncIterator[Browser]:
    playwright: Playwright = await async_playwright().start()
    launch_kwargs: dict = {"headless": headless}
    if proxy:
        launch_kwargs["proxy"] = {
            "server": proxy.server,
            **({"username": proxy.username} if proxy.username else {}),
            **({"password": proxy.password} if proxy.password else {}),
        }
    browser = await playwright.chromium.launch(**launch_kwargs)
    try:
        yield browser
    finally:
        await browser.close()
        await playwright.stop()
