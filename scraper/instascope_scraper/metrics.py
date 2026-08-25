"""Per-profile scrape traffic / pagination metrics (context-local)."""

from __future__ import annotations

import logging
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlparse

logger = logging.getLogger("instascope.scraper.metrics")


@dataclass
class ScrapeMetrics:
    username: str = ""
    started_at: float = field(default_factory=time.monotonic)
    requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    blocked_requests: int = 0
    pagination_requests: int = 0
    pagination_pages: int = 0
    retries: int = 0
    posts_collected: int = 0
    bytes_received: int = 0
    bytes_by_host: dict[str, int] = field(default_factory=dict)
    requests_by_host: dict[str, int] = field(default_factory=dict)

    def host_of(self, url: str) -> str:
        try:
            return (urlparse(url).hostname or "").lower()
        except Exception:
            return ""

    def record_blocked(self, url: str = "") -> None:
        self.blocked_requests += 1
        host = self.host_of(url)
        if host:
            self.requests_by_host[host] = self.requests_by_host.get(host, 0) + 1

    def record_request(self, url: str = "", *, pagination: bool = False) -> None:
        self.requests += 1
        if pagination:
            self.pagination_requests += 1
        host = self.host_of(url)
        if host:
            self.requests_by_host[host] = self.requests_by_host.get(host, 0) + 1

    def record_retry(self) -> None:
        self.retries += 1

    def record_page(self) -> None:
        self.pagination_pages += 1

    def record_response(
        self,
        url: str,
        *,
        status: int | None = None,
        nbytes: int = 0,
        ok: bool | None = None,
    ) -> None:
        if ok is None:
            ok = status is not None and 200 <= int(status) < 400
        if ok:
            self.successful_requests += 1
        else:
            self.failed_requests += 1
        if nbytes > 0:
            self.bytes_received += nbytes
            host = self.host_of(url)
            if host:
                self.bytes_by_host[host] = self.bytes_by_host.get(host, 0) + nbytes

    @property
    def duration_s(self) -> float:
        return max(0.0, time.monotonic() - self.started_at)

    def as_dict(self) -> dict[str, Any]:
        return {
            "username": self.username,
            "total_requests": self.requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "blocked_requests": self.blocked_requests,
            "pagination_requests": self.pagination_requests,
            "pagination_pages": self.pagination_pages,
            "posts_collected": self.posts_collected,
            "retry_count": self.retries,
            "bytes_received": self.bytes_received,
            "scrape_duration_s": round(self.duration_s, 2),
            "bytes_by_host": dict(sorted(self.bytes_by_host.items(), key=lambda kv: -kv[1])[:12]),
            "requests_by_host": dict(sorted(self.requests_by_host.items(), key=lambda kv: -kv[1])[:12]),
        }

    def log_summary(self) -> None:
        d = self.as_dict()
        logger.info(
            "scrape_metrics @%s requests=%s ok=%s fail=%s blocked=%s "
            "pag_req=%s pag_pages=%s posts=%s retries=%s bytes=%s duration=%.1fs",
            d["username"],
            d["total_requests"],
            d["successful_requests"],
            d["failed_requests"],
            d["blocked_requests"],
            d["pagination_requests"],
            d["pagination_pages"],
            d["posts_collected"],
            d["retry_count"],
            d["bytes_received"],
            d["scrape_duration_s"],
        )


_CURRENT: ContextVar[Optional[ScrapeMetrics]] = ContextVar("scrape_metrics", default=None)


def current_metrics() -> ScrapeMetrics | None:
    return _CURRENT.get()


def start_metrics(username: str) -> ScrapeMetrics:
    m = ScrapeMetrics(username=username)
    _CURRENT.set(m)
    return m


def reset_metrics() -> None:
    _CURRENT.set(None)


def m() -> ScrapeMetrics:
    existing = _CURRENT.get()
    if existing is None:
        existing = ScrapeMetrics()
        _CURRENT.set(existing)
    return existing
