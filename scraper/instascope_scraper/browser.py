"""Playwright browser factory with proxy + bandwidth-limited context."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from playwright.async_api import Browser, BrowserContext, Playwright, Route, async_playwright

from instascope_scraper.metrics import m
from instascope_scraper.network_policy import is_pagination_url, should_block_request
from instascope_scraper.types import ProxyConfig


def _launch_timeout_seconds() -> float:
    raw = (os.getenv("SCRAPE_BROWSER_LAUNCH_TIMEOUT_SECONDS") or "60").strip()
    try:
        return max(15.0, float(raw))
    except ValueError:
        return 60.0


async def _on_route(route: Route) -> None:
    request = route.request
    url = request.url
    rtype = request.resource_type
    if should_block_request(url, rtype):
        m().record_blocked(url)
        await route.abort()
        return
    m().record_request(url, pagination=is_pagination_url(url))
    await route.continue_()


async def _on_response(response) -> None:
    try:
        url = response.url
        status = response.status
        nbytes = 0
        headers = response.headers or {}
        cl = headers.get("content-length") or headers.get("Content-Length")
        if cl:
            try:
                nbytes = int(cl)
            except ValueError:
                nbytes = 0
        m().record_response(url, status=status, nbytes=nbytes)
    except Exception:
        pass


async def attach_bandwidth_limits(context: BrowserContext) -> None:
    """Abort images/media/fonts/CSS/static CDN; count remaining bytes."""
    await context.route("**/*", _on_route)
    context.on("response", _on_response)


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
