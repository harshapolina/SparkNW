"""Pydantic API schemas."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field, HttpUrl


# ── Auth ──────────────────────────────────────────────


class SignupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class StudentLoginRequest(BaseModel):
    student_id: str = Field(min_length=1, max_length=64)
    instagram_username: str = Field(min_length=1, max_length=64)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    email: str  # str (not EmailStr) — student accounts use synthetic emails
    name: str
    avatar_url: Optional[str] = None
    role: str = "admin"
    org_id: str = "spark"
    profile_id: Optional[str] = None
    student_id: Optional[str] = None
    created_at: datetime


class AuthResponse(BaseModel):
    user: UserResponse
    tokens: TokenResponse


# ── Profiles ──────────────────────────────────────────


class AddProfileRequest(BaseModel):
    url: str = Field(min_length=5, description="Instagram profile URL or @username")
    student: dict[str, Any] = Field(default_factory=dict)


class UpdateProfileRequest(BaseModel):
    """Change the tracked Instagram handle/URL for an existing profile."""

    url: str = Field(min_length=1, description="Instagram profile URL or @username")


class StudentInfo(BaseModel):
    """Registration-sheet fields shown on profile pages."""

    timestamp: Optional[str] = None
    full_name: Optional[str] = None
    student_id: Optional[str] = None
    program: Optional[str] = None
    year_of_study: Optional[str] = None
    mobile: Optional[str] = None
    email: Optional[str] = None
    university: Optional[str] = None
    instagram_handle: Optional[str] = None
    instagram_url: Optional[str] = None
    instagram_username: Optional[str] = None
    youtube_link: Optional[str] = None
    youtube_username: Optional[str] = None
    youtube_status: str = "Coming soon"
    created_content_before: Optional[str] = None
    current_follower_count_raw: Optional[str] = None
    instagram_followers_declared: Optional[str] = None
    youtube_subscribers_declared: Optional[str] = None
    why_join_spark: Optional[str] = None
    content_interest: Optional[str] = None
    uid: Optional[str] = None
    duplicate_flag: Optional[str] = None
    missing_info: Optional[str] = None


class ProfileResponse(BaseModel):
    id: str
    username: str
    full_name: Optional[str] = None
    bio: Optional[str] = None
    website: Optional[str] = None
    avatar_url: Optional[str] = None
    is_verified: bool = False
    profile_url: str
    followers: int = 0
    following: int = 0
    posts_count: int = 0
    # Posts dated inside SPARK programme window (15 Jul 2026 → today). Not IG lifetime.
    programme_posts: int = 0
    avg_likes: float = 0.0
    avg_views: float = 0.0
    avg_comments: float = 0.0
    engagement_rate: float = 0.0
    growth_pct_today: float = 0.0
    # First successful scrape in the programme window (cannot backfill from IG).
    followers_baseline: Optional[int] = None
    followers_baseline_date: Optional[str] = None  # YYYY-MM-DD
    followers_gained: int = 0  # current − baseline
    followers_gained_pct: float = 0.0
    is_private: bool = False
    is_business: bool = False
    category: Optional[str] = None
    highlight_reel_count: int = 0
    follower_following_ratio: float = 0.0
    insights: dict[str, Any] = Field(default_factory=dict)
    student: dict[str, Any] = Field(default_factory=dict)
    scrape_progress: Optional[dict[str, Any]] = None
    # Minimal YouTube connection refs (metrics live in youtube_* collections)
    youtube_channel_id: Optional[str] = None
    youtube_connected: bool = False
    youtube_last_synced_at: Optional[datetime] = None
    status: str
    last_scraped_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    last_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ProfileListResponse(BaseModel):
    items: list[ProfileResponse]
    total: int
    page: int
    page_size: int


class BulkIdsRequest(BaseModel):
    ids: list[str] = Field(min_length=1)


class BulkImportRow(BaseModel):
    url: str = Field(min_length=1)
    student: dict[str, Any] = Field(default_factory=dict)


class BulkImportRequest(BaseModel):
    urls: list[str] = Field(default_factory=list, max_length=2000)
    rows: list[BulkImportRow] = Field(default_factory=list, max_length=2000)
    scrape_now: bool = True


class BulkImportItemResult(BaseModel):
    url: str
    username: Optional[str] = None
    status: str
    message: Optional[str] = None
    profile_id: Optional[str] = None


class BulkImportResponse(BaseModel):
    imported: int
    skipped: int
    failed: int
    updated: int = 0
    duplicates: int = 0
    scraping: bool
    items: list[BulkImportItemResult]


class BulkExportRequest(BaseModel):
    ids: Optional[list[str]] = None


# ── Posts / Snapshots ─────────────────────────────────


class PostResponse(BaseModel):
    id: str
    profile_id: str
    ig_post_id: str
    shortcode: str
    media_type: str
    caption: Optional[str] = None
    thumbnail_url: Optional[str] = None
    permalink: Optional[str] = None
    likes: int = 0
    comments: int = 0
    views: int = 0
    posted_at: Optional[datetime] = None


class SnapshotResponse(BaseModel):
    id: str
    profile_id: str
    snapshot_date: str
    followers: int
    following: int
    posts_count: int
    avg_likes: float
    avg_views: float
    avg_comments: float
    engagement_rate: float
    followers_growth: int
    followers_growth_pct: float


# ── Jobs / Notifications ──────────────────────────────


class JobResponse(BaseModel):
    id: str
    profile_id: Optional[str] = None
    job_type: str
    status: str
    attempts: int
    error_message: Optional[str] = None
    created_at: datetime
    finished_at: Optional[datetime] = None


class NotificationResponse(BaseModel):
    id: str
    profile_id: Optional[str] = None
    type: str
    title: str
    body: str
    is_read: bool
    created_at: datetime
    meta: dict[str, Any] = Field(default_factory=dict)


# ── Analytics / Overview ──────────────────────────────


class OverviewStats(BaseModel):
    total_profiles: int
    profiles_updated_today: int
    failed_updates: int
    average_engagement: float
    average_followers: float
    average_views: float
    average_likes: float
    follower_growth_today: int


class SeriesPoint(BaseModel):
    date: str
    value: float


class NamedValue(BaseModel):
    name: str
    value: float


class OverviewCharts(BaseModel):
    followers_over_time: list[SeriesPoint]
    posts_per_day: list[SeriesPoint]
    content_types: list[NamedValue]
    posting_heatmap: list[dict[str, Any]]


class OverviewResponse(BaseModel):
    stats: OverviewStats
    charts: OverviewCharts
    recent_updates: list[ProfileResponse]


class ProfileAnalyticsResponse(BaseModel):
    followers_trend: list[SeriesPoint]
    views_trend: list[SeriesPoint]
    likes_trend: list[SeriesPoint]
    comments_trend: list[SeriesPoint]
    posting_frequency: float
    average_engagement: float
    best_posting_day: Optional[str] = None
    best_posting_hour: Optional[int] = None
    growth_pct: float


class MessageResponse(BaseModel):
    message: str


class SettingsResponse(BaseModel):
    dark_mode: bool
    follower_growth_notify_pct: float
    notify_followers_down: bool
    notify_scrape_failed: bool
    notify_engagement_spike: bool
    engagement_spike_pct: float
    timezone: str


class SettingsUpdateRequest(BaseModel):
    dark_mode: Optional[bool] = None
    follower_growth_notify_pct: Optional[float] = None
    notify_followers_down: Optional[bool] = None
    notify_scrape_failed: Optional[bool] = None
    notify_engagement_spike: Optional[bool] = None
    engagement_spike_pct: Optional[float] = None
    timezone: Optional[str] = None


class DailyScrapeSettingsResponse(BaseModel):
    enabled: bool


class DailyScrapeSettingsUpdateRequest(BaseModel):
    enabled: bool


class DailyYouTubeSyncSettingsResponse(BaseModel):
    enabled: bool


class DailyYouTubeSyncSettingsUpdateRequest(BaseModel):
    enabled: bool


class YouTubeConnectRequest(BaseModel):
    url: str = Field(min_length=1, description="Channel URL, @handle, or UC… id")
    # 0 = all uploads on/after programme start (15 Jul); no soft cap.
    max_videos: int = Field(default=0, ge=0, le=50000)
    sync_videos: bool = True


class YouTubeSyncRequest(BaseModel):
    max_videos: int = Field(default=0, ge=0, le=50000)
    fetch_videos: bool = True


class YouTubeChannelResponse(BaseModel):
    profile_id: str
    channel_id: str
    channel_url: Optional[str] = None
    handle: Optional[str] = None
    channel_name: Optional[str] = None
    thumbnail_url: Optional[str] = None
    subscriber_count: Optional[int] = None
    hidden_subscriber_count: bool = False
    view_count: int = 0
    video_count: int = 0
    connected: bool = True
    sync_status: str
    last_error: Optional[str] = None
    last_synced_at: Optional[datetime] = None


class YouTubeResolveResponse(BaseModel):
    channel_id: str
    title: str
    handle: Optional[str] = None
    subscribers: Optional[int] = None
    views: int = 0
    videos: int = 0
    thumbnail: Optional[str] = None


class YouTubeVideoPublic(BaseModel):
    video_id: str
    title: str = ""
    description: str = ""
    url: str = ""
    published_at: Optional[str] = None
    thumbnail_url: Optional[str] = None
    thumbnails: dict[str, Any] = Field(default_factory=dict)
    channel_title: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    category_id: Optional[str] = None
    live_broadcast_content: Optional[str] = None
    default_language: Optional[str] = None
    default_audio_language: Optional[str] = None
    topic_categories: list[str] = Field(default_factory=list)
    recording_date: Optional[str] = None
    live_streaming: dict[str, Any] = Field(default_factory=dict)
    player_embed_html: Optional[str] = None
    localizations: dict[str, Any] = Field(default_factory=dict)
    content_rating: dict[str, Any] = Field(default_factory=dict)
    region_restriction: dict[str, Any] = Field(default_factory=dict)
    view_count: int = 0
    like_count: Optional[int] = None
    comment_count: Optional[int] = None
    favorite_count: Optional[int] = None
    duration: Optional[str] = None
    duration_seconds: Optional[int] = None
    is_short: bool = False
    dimension: Optional[str] = None
    definition: Optional[str] = None
    caption: Optional[str] = None
    licensed_content: Optional[bool] = None
    projection: Optional[str] = None
    privacy_status: Optional[str] = None
    upload_status: Optional[str] = None
    license: Optional[str] = None
    embeddable: Optional[bool] = None
    public_stats_viewable: Optional[bool] = None
    made_for_kids: Optional[bool] = None
    public_api: dict[str, Any] = Field(default_factory=dict)


class YouTubeInsightsResponse(BaseModel):
    connected: bool
    window_from: str
    window_to: str
    channel: Optional[dict[str, Any]] = None
    totals: dict[str, Any] = Field(default_factory=dict)
    videos: list[YouTubeVideoPublic] = Field(default_factory=list)
