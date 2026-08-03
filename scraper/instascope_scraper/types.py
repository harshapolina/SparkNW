"""Scraper DTOs and public API."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional
from urllib.parse import unquote, urlparse


@dataclass
class ProxyConfig:
    server: str
    username: Optional[str] = None
    password: Optional[str] = None


def parse_proxy_url(proxy_url: str | None) -> ProxyConfig | None:
    """Parse http://user:pass@host:port into Playwright-friendly ProxyConfig.

    Playwright needs server (scheme://host:port) separate from username/password.
    Passwords may be URL-encoded (e.g. ~ as %7E).
    """
    if not proxy_url or not str(proxy_url).strip():
        return None
    parsed = urlparse(proxy_url.strip())
    if not parsed.hostname:
        return None
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    scheme = parsed.scheme or "http"
    return ProxyConfig(
        server=f"{scheme}://{parsed.hostname}:{port}",
        username=unquote(parsed.username) if parsed.username else None,
        password=unquote(parsed.password) if parsed.password else None,
    )


def proxy_to_httpx_url(proxy: ProxyConfig | None, *, fallback_env: bool = True) -> str | None:
    """Rebuild a full proxy URL (with auth) for httpx clients.

    Playwright uses split fields; httpx wants http://user:pass@host:port.
    """
    import os
    from urllib.parse import quote

    if proxy and proxy.server:
        if proxy.username is not None and proxy.password is not None:
            user = quote(proxy.username, safe="")
            pwd = quote(proxy.password, safe="")
            # server is scheme://host:port
            rest = proxy.server.split("://", 1)[-1]
            scheme = proxy.server.split("://", 1)[0] if "://" in proxy.server else "http"
            return f"{scheme}://{user}:{pwd}@{rest}"
        if "@" in proxy.server:
            return proxy.server
        # server without auth — prefer full env URL if present
        if fallback_env:
            env = (os.getenv("SCRAPE_PROXY_URL") or "").strip()
            if env:
                return env
        return proxy.server
    if fallback_env:
        env = (os.getenv("SCRAPE_PROXY_URL") or "").strip()
        return env or None
    return None


@dataclass
class ScrapedPost:
    ig_post_id: str
    shortcode: str
    media_type: str
    caption: Optional[str]
    thumbnail_url: Optional[str]
    permalink: Optional[str]
    likes: int
    comments: int
    views: int
    posted_at: Optional[str]
    is_video: bool = False
    accessibility_caption: Optional[str] = None


@dataclass
class ScrapeResult:
    username: str
    ig_user_id: Optional[str]
    full_name: Optional[str]
    bio: Optional[str]
    website: Optional[str]
    avatar_url: Optional[str]
    is_verified: bool
    followers: int
    following: int
    posts_count: int
    posts: list[ScrapedPost] = field(default_factory=list)
    is_private: bool = False
    is_business: bool = False
    category: Optional[str] = None
    pronouns: Optional[str] = None
    highlight_reel_count: int = 0
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "username": self.username,
            "ig_user_id": self.ig_user_id,
            "full_name": self.full_name,
            "bio": self.bio,
            "website": self.website,
            "avatar_url": self.avatar_url,
            "is_verified": self.is_verified,
            "followers": self.followers,
            "following": self.following,
            "posts_count": self.posts_count,
            "is_private": self.is_private,
            "is_business": self.is_business,
            "category": self.category,
            "pronouns": self.pronouns,
            "highlight_reel_count": self.highlight_reel_count,
            "posts": [asdict(p) for p in self.posts],
            "raw": self.raw,
        }
