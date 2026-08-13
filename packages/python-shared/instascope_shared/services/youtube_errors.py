"""YouTube Data API error types — never include API keys in messages."""

from __future__ import annotations


class YouTubeError(Exception):
    """Base error for YouTube Data API operations."""

    def __init__(self, message: str, *, status_code: int | None = None, reason: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.reason = reason or "error"


class YouTubeConfigError(YouTubeError):
    """Missing or invalid server configuration (e.g. no API key)."""

    def __init__(self, message: str = "YOUTUBE_API_KEY is not configured"):
        super().__init__(message, reason="config")


class YouTubeInvalidChannelError(YouTubeError):
    """Channel URL/handle could not be parsed or validated."""

    def __init__(self, message: str = "Invalid YouTube channel URL or handle"):
        super().__init__(message, reason="invalid_channel")


class YouTubeNotFoundError(YouTubeError):
    """Channel or resource does not exist / was deleted."""

    def __init__(self, message: str = "YouTube channel not found"):
        super().__init__(message, status_code=404, reason="not_found")


class YouTubeQuotaExceededError(YouTubeError):
    """Daily YouTube Data API quota exhausted."""

    def __init__(self, message: str = "YouTube API quota exceeded"):
        super().__init__(message, status_code=403, reason="quota_exceeded")


class YouTubeRateLimitError(YouTubeError):
    """Temporary rate limit from Google."""

    def __init__(self, message: str = "YouTube API rate limit"):
        super().__init__(message, status_code=429, reason="rate_limit")


class YouTubeUnavailableError(YouTubeError):
    """Resource exists but public stats are hidden/unavailable."""

    def __init__(self, message: str = "YouTube data unavailable"):
        super().__init__(message, reason="unavailable")


class YouTubeApiError(YouTubeError):
    """Generic YouTube API / network failure."""

    def __init__(
        self,
        message: str = "YouTube API request failed",
        *,
        status_code: int | None = None,
        reason: str = "api_error",
    ):
        super().__init__(message, status_code=status_code, reason=reason)
