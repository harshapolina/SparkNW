"""Scraper DTOs and public API."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass
class ProxyConfig:
    server: str
    username: Optional[str] = None
    password: Optional[str] = None


@dataclass
class ScrapedPost:
    ig_post_id: str
    shortcode: str
    media_type: str
    caption: Optional[str]
    thumbnail_url: Optional[str]
    permalink: Optional[str]
    likes: int
    comments: int
    views: int
    posted_at: Optional[str]
    is_video: bool = False
    accessibility_caption: Optional[str] = None


@dataclass
class ScrapeResult:
    username: str
    ig_user_id: Optional[str]
    full_name: Optional[str]
    bio: Optional[str]
    website: Optional[str]
    avatar_url: Optional[str]
    is_verified: bool
    followers: int
    following: int
    posts_count: int
    posts: list[ScrapedPost] = field(default_factory=list)
    is_private: bool = False
    is_business: bool = False
    category: Optional[str] = None
    pronouns: Optional[str] = None
    highlight_reel_count: int = 0
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "username": self.username,
            "ig_user_id": self.ig_user_id,
            "full_name": self.full_name,
            "bio": self.bio,
            "website": self.website,
            "avatar_url": self.avatar_url,
            "is_verified": self.is_verified,
            "followers": self.followers,
            "following": self.following,
            "posts_count": self.posts_count,
            "is_private": self.is_private,
            "is_business": self.is_business,
            "category": self.category,
            "pronouns": self.pronouns,
            "highlight_reel_count": self.highlight_reel_count,
            "posts": [asdict(p) for p in self.posts],
            "raw": self.raw,
        }
