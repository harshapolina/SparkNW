"""In-memory login throttle — slows credential stuffing / injection sprays."""

from __future__ import annotations

import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

_hits: dict[str, list[float]] = defaultdict(list)


def enforce_auth_rate_limit(request: Request, *, limit: int = 8, window_seconds: int = 60) -> None:
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    ip = forwarded or (request.client.host if request.client else "unknown")
    now = time.monotonic()
    recent = [t for t in _hits[ip] if now - t < window_seconds]
    if len(recent) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many sign-in attempts. Wait a minute and try again.",
        )
    recent.append(now)
    _hits[ip] = recent
