"""Global app config stored in MongoDB (shared by local + cloud API).

Used so Decodo proxy credentials work on the cloud even when Docker Compose
accidentally blanks SCRAPE_PROXY_* env vars.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Optional

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel

logger = logging.getLogger("instascope.app_config")

PROXY_CONFIG_KEY = "scrape_proxy"
DAILY_SCRAPE_CONFIG_KEY = "daily_scrape"
DAILY_YOUTUBE_SYNC_CONFIG_KEY = "daily_youtube_sync"


class AppConfig(Document):
    key: str
    data: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "app_config"
        indexes = [
            IndexModel([("key", ASCENDING)], unique=True),
        ]


def _truthy(v: Any) -> bool:
    return bool(str(v or "").strip())


async def apply_proxy_config_to_env(*, force: bool = False) -> bool:
    """Copy MongoDB scrape proxy settings into os.environ for the scraper pool.

    Returns True if proxy env is available after this call.
    """
    # Already have a working pool from process env / .env
    if not force and (
        _truthy(os.getenv("SCRAPE_PROXY_HOST"))
        or _truthy(os.getenv("SCRAPE_PROXY_URL"))
        or _truthy(os.getenv("SCRAPE_PROXY_URLS"))
    ):
        return True

    try:
        doc = await AppConfig.find_one(AppConfig.key == PROXY_CONFIG_KEY)
    except Exception:
        logger.exception("failed reading app_config scrape_proxy")
        return False
    if not doc or not isinstance(doc.data, dict):
        return False

    data = doc.data
    mapping = {
        "SCRAPE_PROXY_HOST": data.get("host"),
        "SCRAPE_PROXY_USER": data.get("user"),
        "SCRAPE_PROXY_PASS": data.get("password"),
        "SCRAPE_PROXY_PORTS": data.get("ports"),
        "SCRAPE_PROXY_SCHEME": data.get("scheme") or "http",
        "SCRAPE_PROXY_USER_PREFIX": data.get("user_prefix")
        if data.get("user_prefix") is not None
        else "user-",
        "SCRAPE_PROXY_SESSION_ROTATE": str(data.get("session_rotate", "1")),
        "SCRAPE_PROXY_URL": data.get("url"),
        "SCRAPE_PROXY_URLS": data.get("urls"),
    }
    applied = 0
    for key, val in mapping.items():
        if val is None:
            continue
        text = str(val).strip()
        if not text:
            continue
        # Only fill blanks unless forcing — never wipe a good compose/.env value.
        if force or not (os.getenv(key) or "").strip():
            os.environ[key] = text
            applied += 1

    if applied:
        # Force proxy pool to reload
        try:
            from instascope_scraper.proxy_pool import load_proxy_urls

            load_proxy_urls(force_reload=True)
        except Exception:
            logger.exception("proxy pool reload after app_config failed")
        logger.info(
            "loaded scrape proxy config from MongoDB (keys=%s, host=%s, ports=%s)",
            applied,
            (os.getenv("SCRAPE_PROXY_HOST") or "")[:40],
            (os.getenv("SCRAPE_PROXY_PORTS") or "")[:60],
        )
        return True
    return bool(
        (os.getenv("SCRAPE_PROXY_HOST") or "").strip()
        or (os.getenv("SCRAPE_PROXY_URL") or "").strip()
    )


async def upsert_proxy_config(data: dict[str, Any]) -> AppConfig:
    doc = await AppConfig.find_one(AppConfig.key == PROXY_CONFIG_KEY)
    if not doc:
        doc = AppConfig(key=PROXY_CONFIG_KEY, data=data, updated_at=datetime.utcnow())
        await doc.insert()
        return doc
    merged = dict(doc.data or {})
    for k, v in data.items():
        if v is not None:
            merged[k] = v
    doc.data = merged
    doc.updated_at = datetime.utcnow()
    await doc.save()
    await apply_proxy_config_to_env(force=True)
    return doc


async def is_daily_scrape_enabled() -> bool:
    """Whether Celery Beat daily fan-out should enqueue scrapes.

    Defaults to True when unset so existing deployments keep scraping until
    an admin turns the toggle off (e.g. Decodo bandwidth exhausted).
    """
    try:
        doc = await AppConfig.find_one(AppConfig.key == DAILY_SCRAPE_CONFIG_KEY)
    except Exception:
        logger.exception("failed reading app_config daily_scrape")
        return True
    if not doc or not isinstance(doc.data, dict):
        return True
    enabled = doc.data.get("enabled")
    if enabled is None:
        return True
    return bool(enabled)


async def set_daily_scrape_enabled(enabled: bool) -> bool:
    """Persist the admin daily-scrape toggle. Returns the stored value."""
    data = {"enabled": bool(enabled)}
    doc = await AppConfig.find_one(AppConfig.key == DAILY_SCRAPE_CONFIG_KEY)
    if not doc:
        doc = AppConfig(
            key=DAILY_SCRAPE_CONFIG_KEY,
            data=data,
            updated_at=datetime.utcnow(),
        )
        await doc.insert()
        return bool(enabled)
    merged = dict(doc.data or {})
    merged["enabled"] = bool(enabled)
    doc.data = merged
    doc.updated_at = datetime.utcnow()
    await doc.save()
    return bool(enabled)


async def is_daily_youtube_sync_enabled() -> bool:
    """Whether Celery Beat should fan out YouTube syncs.

    Independent of Instagram daily-scrape toggle.
    Defaults to True when unset (same idea as Instagram daily scrape) so mornings
    refresh connected channels automatically after deploy.
    """
    try:
        doc = await AppConfig.find_one(AppConfig.key == DAILY_YOUTUBE_SYNC_CONFIG_KEY)
    except Exception:
        logger.exception("failed reading app_config daily_youtube_sync")
        return True
    if not doc or not isinstance(doc.data, dict):
        return True
    enabled = doc.data.get("enabled")
    if enabled is None:
        return True
    return bool(enabled)


async def set_daily_youtube_sync_enabled(enabled: bool) -> bool:
    data = {"enabled": bool(enabled)}
    doc = await AppConfig.find_one(AppConfig.key == DAILY_YOUTUBE_SYNC_CONFIG_KEY)
    if not doc:
        doc = AppConfig(
            key=DAILY_YOUTUBE_SYNC_CONFIG_KEY,
            data=data,
            updated_at=datetime.utcnow(),
        )
        await doc.insert()
        return bool(enabled)
    merged = dict(doc.data or {})
    merged["enabled"] = bool(enabled)
    doc.data = merged
    doc.updated_at = datetime.utcnow()
    await doc.save()
    return bool(enabled)
