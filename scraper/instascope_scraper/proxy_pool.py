"""Residential proxy pool with round-robin rotation (Decodo multi-port friendly).

Env (any combination works):

1) Host + ports (recommended for Decodo):
   SCRAPE_PROXY_HOST=gate.decodo.com
   SCRAPE_PROXY_USER=spkfh3mdm6
   SCRAPE_PROXY_PASS=...
   SCRAPE_PROXY_PORTS=10001,10002,10003,10004,10005,10006,10007
   SCRAPE_PROXY_SCHEME=http

2) Comma / newline list of full URLs:
   SCRAPE_PROXY_URLS=http://u:p@host:10001,http://u:p@host:10002

3) Single URL (legacy):
   SCRAPE_PROXY_URL=http://u:p@host:10001
"""

from __future__ import annotations

import logging
import os
import threading
import time
from urllib.parse import quote

from instascope_scraper.types import ProxyConfig, parse_proxy_url, proxy_to_httpx_url

logger = logging.getLogger("instascope.scraper.proxy_pool")

_lock = threading.Lock()
_urls: list[str] | None = None
_rr = 0
# url -> unix time until which we skip this proxy after rate-limit / tunnel fail
_cooldown_until: dict[str, float] = {}


def _split_list(raw: str) -> list[str]:
    parts: list[str] = []
    for chunk in raw.replace("\n", ",").replace(";", ",").split(","):
        item = chunk.strip()
        if item:
            parts.append(item)
    return parts


def _build_url(scheme: str, user: str, password: str, host: str, port: str) -> str:
    u = quote(user, safe="")
    p = quote(password, safe="")
    return f"{scheme}://{u}:{p}@{host}:{port}"


def load_proxy_urls(*, force_reload: bool = False) -> list[str]:
    """Return configured proxy URLs (deduped, stable order)."""
    global _urls
    with _lock:
        if _urls is not None and not force_reload:
            return list(_urls)

        found: list[str] = []

        multi = (os.getenv("SCRAPE_PROXY_URLS") or "").strip()
        if multi:
            found.extend(_split_list(multi))

        host = (os.getenv("SCRAPE_PROXY_HOST") or "").strip()
        user = (os.getenv("SCRAPE_PROXY_USER") or "").strip()
        password = os.getenv("SCRAPE_PROXY_PASS")
        ports_raw = (os.getenv("SCRAPE_PROXY_PORTS") or "").strip()
        scheme = (os.getenv("SCRAPE_PROXY_SCHEME") or "http").strip() or "http"
        if host and user and password is not None and ports_raw:
            for port in _split_list(ports_raw):
                found.append(_build_url(scheme, user, password, host, port))

        single = (os.getenv("SCRAPE_PROXY_URL") or "").strip()
        if single:
            found.append(single)

        # Dedupe by host:port (encoded vs raw password URLs collapse)
        seen_hosts: set[str] = set()
        urls: list[str] = []
        for u in found:
            cfg = parse_proxy_url(u)
            if cfg is None:
                logger.warning("skipping unparseable proxy URL: %s", u.split("@")[-1])
                continue
            key = cfg.server.lower()
            if key in seen_hosts:
                continue
            seen_hosts.add(key)
            urls.append(u)

        _urls = urls
        if urls:
            ports = []
            for u in urls:
                cfg = parse_proxy_url(u)
                if cfg and ":" in cfg.server:
                    ports.append(cfg.server.rsplit(":", 1)[-1])
            logger.info(
                "proxy pool loaded size=%s ports=%s",
                len(urls),
                ",".join(ports[:12]) + ("…" if len(ports) > 12 else ""),
            )
        else:
            logger.info("proxy pool empty — scrapes will use direct IP")
        return list(urls)


def pool_size() -> int:
    return len(load_proxy_urls())


def _cooldown_seconds() -> float:
    raw = (os.getenv("SCRAPE_PROXY_COOLDOWN_SECONDS") or "90").strip()
    try:
        return max(15.0, float(raw))
    except ValueError:
        return 90.0


def mark_proxy_bad(proxy: ProxyConfig | str | None, *, seconds: float | None = None) -> None:
    """Temporarily skip a proxy after rate-limit / tunnel failure."""
    url: str | None = None
    if isinstance(proxy, str):
        url = proxy
    elif proxy is not None:
        url = proxy_to_httpx_url(proxy, fallback_env=False)
    if not url:
        return
    until = time.time() + (seconds if seconds is not None else _cooldown_seconds())
    with _lock:
        _cooldown_until[url] = until
    logger.warning(
        "proxy cooldown %ss → %s",
        int(until - time.time()),
        url.split("@")[-1] if "@" in url else url,
    )


def next_proxy(*, exclude: ProxyConfig | str | None = None) -> ProxyConfig | None:
    """Round-robin pick next healthy proxy from the pool."""
    urls = load_proxy_urls()
    if not urls:
        return None

    exclude_url: str | None = None
    if isinstance(exclude, str):
        exclude_url = exclude
    elif exclude is not None:
        exclude_url = proxy_to_httpx_url(exclude, fallback_env=False)

    now = time.time()
    with _lock:
        global _rr
        n = len(urls)
        for _ in range(n):
            idx = _rr % n
            _rr += 1
            url = urls[idx]
            if exclude_url and url == exclude_url and n > 1:
                continue
            cool = _cooldown_until.get(url, 0.0)
            if cool > now and n > 1:
                continue
            cfg = parse_proxy_url(url)
            if cfg:
                logger.info("proxy pick → %s", cfg.server)
                return cfg

        # All cooling down — pick next anyway
        url = urls[_rr % n]
        _rr += 1
        cfg = parse_proxy_url(url)
        if cfg:
            logger.info("proxy pick (all cooling) → %s", cfg.server)
        return cfg


def all_proxy_httpx_urls() -> list[str]:
    """All pool URLs for pagination failover cycles."""
    return load_proxy_urls()


def proxy_label(proxy: ProxyConfig | None) -> str:
    if not proxy:
        return "direct"
    return proxy.server
