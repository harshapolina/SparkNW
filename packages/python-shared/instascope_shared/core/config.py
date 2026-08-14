"""Application settings — MongoDB + Redis + auth."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "InstaScope"
    environment: str = "development"
    debug: bool = True
    api_prefix: str = "/api/v1"

    # Provide your Atlas / self-hosted URI via MONGODB_URI
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "instascope"

    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "change-me-in-production-use-long-random-string"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14

    cors_origins: str = "http://localhost:3000"
    # Optional single web app origin (e.g. http://62.238.57.52:3000) merged into CORS allowlist
    web_origin: str | None = None

    scrape_delay_seconds: float = 2.0
    scrape_max_retries: int = 3
    scrape_proxy_url: str | None = None
    # Optional multi-proxy (Decodo ports). Prefer these over a single URL when set.
    scrape_proxy_urls: str | None = None
    scrape_proxy_host: str | None = None
    scrape_proxy_user: str | None = None
    scrape_proxy_pass: str | None = None
    scrape_proxy_ports: str | None = None
    scrape_proxy_scheme: str = "http"
    scrape_headless: bool = True
    # Daily auto-scrape (Celery Beat). Default 08:00 Asia/Kolkata (IST).
    celery_timezone: str = "Asia/Kolkata"
    daily_scrape_hour_ist: int = 8
    daily_scrape_minute_ist: int = 0
    # Seconds between each profile enqueue so proxies are not hammered at once.
    daily_scrape_stagger_seconds: float = 12.0
    # Legacy alias — ignored when IST hour/minute are set (kept for old .env files).
    daily_scrape_hour_utc: int = 3

    follower_growth_notify_pct: float = 5.0
    engagement_spike_notify_pct: float = 50.0

    # YouTube Data API — scoring stays off until SPARK rules are provided.
    youtube_scoring_enabled: bool = True
    youtube_api_key: str | None = None
    # Daily YouTube sync (Celery Beat) — own toggle in Mongo later; schedule defaults.
    daily_youtube_sync_hour_ist: int = 8
    daily_youtube_sync_minute_ist: int = 0
    daily_youtube_sync_stagger_seconds: float = 2.0

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        if self.web_origin and self.web_origin.strip():
            origins.append(self.web_origin.strip())
        return list(dict.fromkeys(origins))


@lru_cache
def get_settings() -> Settings:
    return Settings()
