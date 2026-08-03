"""Beanie document models — normalized collections for scale."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from beanie import Document, Indexed
from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel


class ProfileStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


class JobType(str, Enum):
    SCRAPE_PROFILE = "scrape_profile"
    BULK_REFRESH = "bulk_refresh"
    RECOMPUTE_METRICS = "recompute_metrics"


class MediaType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    CAROUSEL = "carousel"
    REEL = "reel"
    UNKNOWN = "unknown"


class NotificationType(str, Enum):
    FOLLOWERS_UP = "followers_up"
    FOLLOWERS_DOWN = "followers_down"
    PROFILE_UNAVAILABLE = "profile_unavailable"
    SCRAPE_FAILED = "scrape_failed"
    ENGAGEMENT_SPIKE = "engagement_spike"
    SYSTEM = "system"


class User(Document):
    email: Indexed(str, unique=True)  # type: ignore[valid-type]
    password_hash: str
    name: str
    avatar_url: Optional[str] = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "users"


class UserSettings(Document):
    user_id: Indexed(str)  # type: ignore[valid-type]
    dark_mode: bool = False
    follower_growth_notify_pct: float = 5.0
    notify_followers_down: bool = True
    notify_scrape_failed: bool = True
    notify_engagement_spike: bool = True
    engagement_spike_pct: float = 50.0
    timezone: str = "UTC"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "user_settings"
        indexes = [
            IndexModel([("user_id", ASCENDING)], unique=True),
        ]


class Profile(Document):
    """Current profile state. Historical metrics live in ProfileSnapshot."""

    user_id: Indexed(str)  # type: ignore[valid-type]
    username: Indexed(str)  # type: ignore[valid-type]
    ig_user_id: Optional[str] = None
    full_name: Optional[str] = None
    bio: Optional[str] = None
    website: Optional[str] = None
    avatar_url: Optional[str] = None
    is_verified: bool = False
    profile_url: str

    # Cached current metrics (updated after each successful scrape)
    followers: int = 0
    following: int = 0
    posts_count: int = 0
    avg_likes: float = 0.0
    avg_views: float = 0.0
    avg_comments: float = 0.0
    engagement_rate: float = 0.0
    growth_pct_today: float = 0.0

    # Extra exact profile flags + derived insights (from last scrape)
    is_private: bool = False
    is_business: bool = False
    category: Optional[str] = None
    highlight_reel_count: int = 0
    follower_following_ratio: float = 0.0
    insights: dict = Field(default_factory=dict)

    status: ProfileStatus = ProfileStatus.ACTIVE
    last_scraped_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    last_error: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "profiles"
        indexes = [
            IndexModel([("user_id", ASCENDING), ("username", ASCENDING)], unique=True),
            IndexModel([("user_id", ASCENDING), ("status", ASCENDING)]),
            IndexModel([("status", ASCENDING), ("last_scraped_at", ASCENDING)]),
        ]


class Post(Document):
    profile_id: Indexed(str)  # type: ignore[valid-type]
    user_id: Indexed(str)  # type: ignore[valid-type]
    ig_post_id: Indexed(str, unique=True)  # type: ignore[valid-type]
    shortcode: str
    media_type: MediaType = MediaType.UNKNOWN
    caption: Optional[str] = None
    thumbnail_url: Optional[str] = None
    permalink: Optional[str] = None
    likes: int = 0
    comments: int = 0
    views: int = 0
    posted_at: Optional[datetime] = None
    scraped_at: datetime = Field(default_factory=datetime.utcnow)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "posts"
        indexes = [
            IndexModel([("profile_id", ASCENDING), ("posted_at", DESCENDING)]),
            IndexModel([("user_id", ASCENDING), ("posted_at", DESCENDING)]),
        ]


class ProfileSnapshot(Document):
    """Immutable daily point-in-time metrics. Charts read this collection."""

    profile_id: Indexed(str)  # type: ignore[valid-type]
    user_id: Indexed(str)  # type: ignore[valid-type]
    snapshot_date: str  # YYYY-MM-DD (UTC)
    followers: int = 0
    following: int = 0
    posts_count: int = 0
    avg_likes: float = 0.0
    avg_views: float = 0.0
    avg_comments: float = 0.0
    engagement_rate: float = 0.0
    followers_growth: int = 0
    followers_growth_pct: float = 0.0
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "profile_snapshots"
        indexes = [
            IndexModel(
                [("profile_id", ASCENDING), ("snapshot_date", ASCENDING)],
                unique=True,
            ),
            IndexModel([("user_id", ASCENDING), ("snapshot_date", ASCENDING)]),
        ]


class Job(Document):
    user_id: Indexed(str)  # type: ignore[valid-type]
    profile_id: Optional[str] = None
    job_type: JobType = JobType.SCRAPE_PROFILE
    status: JobStatus = JobStatus.PENDING
    priority: int = 5
    attempts: int = 0
    max_attempts: int = 3
    error_message: Optional[str] = None
    celery_task_id: Optional[str] = None
    scheduled_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "jobs"
        indexes = [
            IndexModel([("status", ASCENDING), ("scheduled_at", ASCENDING)]),
            IndexModel([("profile_id", ASCENDING), ("created_at", DESCENDING)]),
            IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)]),
        ]


class ScrapeLog(Document):
    job_id: Optional[str] = None
    profile_id: Optional[str] = None
    user_id: Optional[str] = None
    level: str = "info"
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "scrape_logs"
        indexes = [
            IndexModel([("profile_id", ASCENDING), ("created_at", DESCENDING)]),
            IndexModel([("job_id", ASCENDING)]),
        ]


class Notification(Document):
    user_id: Indexed(str)  # type: ignore[valid-type]
    profile_id: Optional[str] = None
    type: NotificationType
    title: str
    body: str
    is_read: bool = False
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "notifications"
        indexes = [
            IndexModel([("user_id", ASCENDING), ("is_read", ASCENDING), ("created_at", DESCENDING)]),
        ]


DOCUMENT_MODELS = [
    User,
    UserSettings,
    Profile,
    Post,
    ProfileSnapshot,
    Job,
    ScrapeLog,
    Notification,
]
