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

    scrape_delay_seconds: float = 2.0
    scrape_max_retries: int = 3
    scrape_proxy_url: str | None = None
    scrape_headless: bool = True
    daily_scrape_hour_utc: int = 3

    follower_growth_notify_pct: float = 5.0
    engagement_spike_notify_pct: float = 50.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
