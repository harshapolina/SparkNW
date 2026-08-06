"""Residential proxy pool with round-robin + Decodo session rotation.

Env (any combination works):

1) Host + ports (recommended for Decodo):
   SCRAPE_PROXY_HOST=gate.decodo.com
   SCRAPE_PROXY_USER=spkfh3mdm6
   SCRAPE_PROXY_PASS=...
   SCRAPE_PROXY_PORTS=7000,10001,10002,10003,10004,10005,10006,10007
   # 7000/10000 = rotating; 10001+ = sticky endpoint ports
   SCRAPE_PROXY_SCHEME=http
   SCRAPE_PROXY_SESSION_ROTATE=1
   SCRAPE_PROXY_USER_PREFIX=user-

2) Comma / newline list of full URLs:
   SCRAPE_PROXY_URLS=http://u:p@host:10001,http://u:p@host:10002

3) Single URL (legacy):
   SCRAPE_PROXY_URL=http://u:p@host:10001
"""

from __future__ import annotations

import logging
import os
import secrets
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


def _user_prefix() -> str:
    raw = (os.getenv("SCRAPE_PROXY_USER_PREFIX") or "user-").strip()
    # Allow empty to disable
    if raw.lower() in {"0", "false", "no", "none"}:
        return ""
    return raw


def _session_rotate_enabled() -> bool:
    return (os.getenv("SCRAPE_PROXY_SESSION_ROTATE") or "1").strip().lower() not in {
        "0",
        "false",
        "no",
    }


def _decorate_username(base_user: str, *, sticky: bool) -> str:
    """Build Decodo username.

    Docs: parameters require `user-` prefix.
    Rotating: user-{name} (or user-{name}-session-{id} for sticky-on-rotating-port).
    Sticky ports (10001+): unique session IDs still help isolate bad exits.
    """
    prefix = _user_prefix()
    user = base_user
    if prefix and not user.startswith(prefix):
        user = f"{prefix}{user}"
    if not _session_rotate_enabled():
        return user
    sid = secrets.token_hex(4)
    # Sticky session for the length of one scrape (~10 min)
    return f"{user}-session-{sid}-sessionduration-10"


def _build_url(scheme: str, user: str, password: str, host: str, port: str) -> str:
    u = quote(user, safe="")
    p = quote(password, safe="")
    return f"{scheme}://{u}:{p}@{host}:{port}"


def _base_credentials() -> tuple[str, str, str, str] | None:
    host = (os.getenv("SCRAPE_PROXY_HOST") or "").strip()
    user = (os.getenv("SCRAPE_PROXY_USER") or "").strip()
    password = os.getenv("SCRAPE_PROXY_PASS")
    scheme = (os.getenv("SCRAPE_PROXY_SCHEME") or "http").strip() or "http"
    if host and user and password is not None:
        return scheme, user, password, host
    return None


def load_proxy_urls(*, force_reload: bool = False) -> list[str]:
    """Return configured proxy URL templates (deduped by host:port).

    Session IDs are injected at pick-time via next_proxy(), not here.
    """
    global _urls
    with _lock:
        if _urls is not None and not force_reload:
            return list(_urls)

        found: list[str] = []

        multi = (os.getenv("SCRAPE_PROXY_URLS") or "").strip()
        if multi:
            found.extend(_split_list(multi))

        creds = _base_credentials()
        ports_raw = (os.getenv("SCRAPE_PROXY_PORTS") or "").strip()
        if creds and ports_raw:
            scheme, user, password, host = creds
            # Prefer rotating ports first for fresh IPs
            ports = _split_list(ports_raw)
            rotating = [p for p in ports if p in {"7000", "10000"}]
            sticky = [p for p in ports if p not in {"7000", "10000"}]
            ordered = rotating + sticky
            for port in ordered:
                # Template without session — next_proxy adds session
                found.append(_build_url(scheme, user, password, host, port))

        single = (os.getenv("SCRAPE_PROXY_URL") or "").strip()
        if single:
            found.append(single)

        # Dedupe by host:port
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
                "proxy pool loaded size=%s ports=%s session_rotate=%s",
                len(urls),
                ",".join(ports[:12]) + ("…" if len(ports) > 12 else ""),
                _session_rotate_enabled(),
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
    # Cool down by host:port (ignore session id in username)
    cfg = parse_proxy_url(url)
    key = cfg.server if cfg else url
    until = time.time() + (seconds if seconds is not None else _cooldown_seconds())
    with _lock:
        _cooldown_until[key] = until
    logger.warning("proxy cooldown %ss → %s", int(until - time.time()), key)


def _with_fresh_session(url: str) -> str:
    """Rebuild URL with a fresh Decodo session id so each pick gets a new exit IP."""
    creds = _base_credentials()
    cfg = parse_proxy_url(url)
    if not creds or not cfg:
        return url
    scheme, base_user, password, host = creds
    port = cfg.server.rsplit(":", 1)[-1]
    sticky = port not in {"7000", "10000"}
    user = _decorate_username(base_user, sticky=sticky)
    return _build_url(scheme, user, password, host, port)


def next_proxy(*, exclude: ProxyConfig | str | None = None) -> ProxyConfig | None:
    """Round-robin pick next healthy proxy from the pool (fresh session each time)."""
    urls = load_proxy_urls()
    if not urls:
        return None

    exclude_server: str | None = None
    if isinstance(exclude, str):
        ecfg = parse_proxy_url(exclude)
        exclude_server = ecfg.server if ecfg else None
    elif exclude is not None:
        exclude_server = exclude.server

    now = time.time()
    with _lock:
        global _rr
        n = len(urls)
        for _ in range(n):
            idx = _rr % n
            _rr += 1
            url = urls[idx]
            cfg0 = parse_proxy_url(url)
            server = cfg0.server if cfg0 else url
            if exclude_server and server == exclude_server and n > 1:
                continue
            cool = _cooldown_until.get(server, 0.0)
            if cool > now and n > 1:
                continue
            fresh = _with_fresh_session(url)
            cfg = parse_proxy_url(fresh)
            if cfg:
                logger.info("proxy pick → %s user=%s", cfg.server, (cfg.username or "")[:48])
                return cfg

        # All cooling down — pick next anyway with fresh session
        url = urls[_rr % n]
        _rr += 1
        fresh = _with_fresh_session(url)
        cfg = parse_proxy_url(fresh)
        if cfg:
            logger.info("proxy pick (all cooling) → %s", cfg.server)
        return cfg


def all_proxy_httpx_urls() -> list[str]:
    """Fresh-session URLs for every pool port (pagination failover)."""
    return [_with_fresh_session(u) for u in load_proxy_urls()]


def proxy_label(proxy: ProxyConfig | None) -> str:
    if not proxy:
        return "direct"
    return proxy.server
