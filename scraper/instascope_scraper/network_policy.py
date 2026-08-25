"""Playwright route policy: drop bytes we never parse.

Inspected Decodo split (~25 GB):
- instagram.com ~13.8 GB: HTML documents + GraphQL/feed JSON (required for data)
- static.cdninstagram.com ~10.8 GB: React/CSS/font bundles loaded by Playwright
- scontent.cdninstagram.com ~99 MB: user photos/videos (URLs stored; bytes unused)

Data APIs live on www.instagram.com / i.instagram.com (document, xhr, fetch).
static.cdninstagram.com is the web-app static CDN, not the pagination API.
scontent is media CDN; we already receive thumbnail URLs in JSON.
"""

from __future__ import annotations

from urllib.parse import urlparse

# Resource types Playwright never needs for JSON/meta extraction or in-page fetch().
BLOCK_RESOURCE_TYPES = frozenset(
    {
        "image",
        "media",
        "font",
        "stylesheet",
        "websocket",
        "manifest",
        "ping",
        "texttrack",
        "imageset",
    }
)

# Hosts that only serve pixels / media / app chrome — never feed JSON.
BLOCK_HOST_SUFFIXES = (
    "scontent.cdninstagram.com",
    "scontent.instagram.com",
    "cdn.fbsbx.com",
    "fbcdn.net",
)

BLOCK_HOST_EXACT = frozenset(
    {
        "static.cdninstagram.com",
        "static.xx.fbcdn.net",
        "connect.facebook.net",
        "www.google-analytics.com",
        "www.googletagmanager.com",
        "googleads.g.doubleclick.net",
    }
)

# Allow API + HTML. Scripts on instagram.com itself are rare; GraphQL is xhr/fetch.
ALLOW_HOST_SUFFIXES = (
    "instagram.com",
)


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def should_block_request(url: str, resource_type: str | None = None) -> bool:
    """Return True when this request is not required to collect scrape fields."""
    host = _host(url)
    rtype = (resource_type or "").lower()
    if rtype in BLOCK_RESOURCE_TYPES:
        return True
    if not host:
        return False
    if host in BLOCK_HOST_EXACT:
        return True
    if any(host == s or host.endswith("." + s) for s in BLOCK_HOST_SUFFIXES):
        return True
    # static.cdninstagram.com already in BLOCK_HOST_EXACT.
    # Keep www/i.instagram.com documents + xhr/fetch + scripts (cookie/banner).
    return False


def is_pagination_url(url: str) -> bool:
    u = url.lower()
    return (
        "/api/v1/feed/user/" in u
        or "/graphql/query" in u
        or "max_id=" in u
        or "query_hash=" in u
        or "doc_id=" in u
    )
