"""Request-scoped scrape caps via contextvars (no os.environ mutation)."""

from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator


@dataclass
class ScrapeCaps:
    max_posts: int = 0
    enrich_max: int = 0
    max_retries: int = 3
    use_browser: bool = True
    browser_on_partial: bool = False
    strict: bool = False
    page_delay_seconds: float | None = None


_active_caps: ContextVar[ScrapeCaps | None] = ContextVar("scrape_caps", default=None)

_CAPS_ENV_KEYS = frozenset(
    {
        "SCRAPE_MAX_POSTS",
        "SCRAPE_ENRICH_MAX",
        "SCRAPE_MAX_RETRIES",
        "SCRAPE_USE_BROWSER",
        "SCRAPE_BROWSER_ON_PARTIAL",
        "SCRAPE_STRICT",
        "SCRAPE_PAGE_DELAY_SECONDS",
    }
)


@contextmanager
def use_caps(caps: ScrapeCaps) -> Iterator[None]:
    """Activate ``caps`` for the current context (and child tasks that copy it)."""
    token = _active_caps.set(caps)
    try:
        yield
    finally:
        _active_caps.reset(token)


def caps_env(name: str, default: str = "") -> str:
    """Return override from active ScrapeCaps for known keys, else ``os.getenv``."""
    caps = _active_caps.get()
    if caps is not None and name in _CAPS_ENV_KEYS:
        if name == "SCRAPE_MAX_POSTS":
            return str(caps.max_posts)
        if name == "SCRAPE_ENRICH_MAX":
            return str(caps.enrich_max)
        if name == "SCRAPE_MAX_RETRIES":
            return str(caps.max_retries)
        if name == "SCRAPE_USE_BROWSER":
            return "1" if caps.use_browser else "0"
        if name == "SCRAPE_BROWSER_ON_PARTIAL":
            return "1" if caps.browser_on_partial else "0"
        if name == "SCRAPE_STRICT":
            return "1" if caps.strict else "0"
        if name == "SCRAPE_PAGE_DELAY_SECONDS":
            if caps.page_delay_seconds is None:
                return os.getenv(name, default)
            return str(caps.page_delay_seconds)
    return os.getenv(name, default)


def _env_truthy(raw: str) -> bool:
    return raw.strip().lower() not in {"0", "false", "no", ""}


def caps_for_api(source: str) -> ScrapeCaps:
    """Build ScrapeCaps from SCRAPE_INLINE_* env (API single/bulk scrapes)."""
    from instascope_scraper.proxy_pool import pool_size

    max_posts = int((os.getenv("SCRAPE_INLINE_MAX_POSTS") or "0").strip() or "0")
    if source == "bulk":
        bulk_raw = (os.getenv("SCRAPE_BULK_MAX_POSTS") or "").strip()
        if bulk_raw:
            max_posts = int(bulk_raw)

    enrich_max = int((os.getenv("SCRAPE_INLINE_ENRICH_MAX") or "12").strip() or "12")
    max_retries = int((os.getenv("SCRAPE_INLINE_MAX_RETRIES") or "1").strip() or "1")

    if "SCRAPE_INLINE_USE_BROWSER" in os.environ:
        use_browser = _env_truthy(
            (os.environ.get("SCRAPE_INLINE_USE_BROWSER") or "0").strip() or "0"
        )
    else:
        use_browser = pool_size() > 0

    browser_on_partial = (
        (os.getenv("SCRAPE_INLINE_BROWSER_ON_PARTIAL") or "0").strip() or "0"
    ) == "1"
    strict = ((os.getenv("SCRAPE_INLINE_STRICT") or "0").strip() or "0") == "1"
    page_delay = float(
        (os.getenv("SCRAPE_INLINE_PAGE_DELAY_SECONDS") or "0.35").strip() or "0.35"
    )

    return ScrapeCaps(
        max_posts=max_posts,
        enrich_max=enrich_max,
        max_retries=max_retries,
        use_browser=use_browser,
        browser_on_partial=browser_on_partial,
        strict=strict,
        page_delay_seconds=page_delay,
    )
