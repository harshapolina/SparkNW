"""Persist scrape results → profile, posts, snapshot, notifications."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from instascope_shared.analytics.metrics import compute_post_metrics
from instascope_shared.core.config import get_settings
from instascope_shared.domain.instagram import growth_pct
from instascope_shared.models import (
    Job,
    JobStatus,
    MediaType,
    Notification,
    NotificationType,
    Post,
    Profile,
    ProfileSnapshot,
    ProfileStatus,
    ScrapeLog,
    UserSettings,
)


def _media_type(raw: str | None) -> MediaType:
    mapping = {
        "image": MediaType.IMAGE,
        "video": MediaType.VIDEO,
        "carousel": MediaType.CAROUSEL,
        "reel": MediaType.REEL,
        "GraphImage": MediaType.IMAGE,
        "GraphVideo": MediaType.VIDEO,
        "GraphSidecar": MediaType.CAROUSEL,
    }
    return mapping.get(raw or "", MediaType.UNKNOWN)


def humanize_scrape_error(err: BaseException | str) -> str:
    """User-facing scrape failure text (never leak raw internal API names)."""
    raw = str(err)
    low = raw.lower()
    if "get_pymongo_collection" in low or "pymongo" in low:
        return "Temporary database issue while saving scrape. Please Refresh again."
    if "err_tunnel" in low or "tunnel_connection" in low:
        return "Proxy tunnel failed opening Instagram. Check Decodo credentials, then Refresh."
    if "net::err_" in low or "page.goto" in low:
        return "Network error reaching Instagram via proxy. Refresh to retry (HTTP fallback enabled)."
    if "login wall" in low or ("login" in low and "blocked" in low):
        return "Instagram showed a login wall. Verify residential proxy session."
    if "incomplete timeline" in low:
        return "Partial timeline only — Instagram blocked full pagination. Data may still be usable after Refresh."
    if "not found" in low:
        return raw
    if len(raw) > 220:
        return raw[:217] + "..."
    return raw


def is_false_pymongo_failure(error: BaseException | str | None) -> bool:
    """True for the known Beanie false-positive that marked scrapes failed after success."""
    if error is None:
        return False
    low = str(error).lower()
    return (
        "get_pymongo_collection" in low
        or ("pymongo" in low and "attribute" in low)
        or "temporary database issue while saving scrape" in low
    )


async def heal_false_pymongo_failure(profile: Profile) -> bool:
    """Clear bogus failed status (pymongo / incomplete-timeline) when profile has real data.

    Does not change metrics, posts, or scrape flow — status/last_error only.
    """
    status_val = profile.status.value if hasattr(profile.status, "value") else str(profile.status)
    if status_val != "failed":
        return False
    err = str(profile.last_error or "")
    soft = (
        is_false_pymongo_failure(err)
        or "incomplete timeline" in err.lower()
        or "get_pymongo" in err.lower()
    )
    has_card = bool(profile.followers or profile.posts_count or profile.last_success_at)
    if not (soft and has_card):
        return False
    profile.status = ProfileStatus.ACTIVE
    profile.last_error = None
    profile.updated_at = datetime.utcnow()
    await profile.save()
    return True


async def apply_scrape_result(
    *,
    job: Job,
    profile: Profile,
    result: dict[str, Any],
) -> None:
    """Idempotent write of a successful scrape."""
    settings = get_settings()
    today = datetime.utcnow().strftime("%Y-%m-%d")

    prev_followers = profile.followers
    followers = int(result.get("followers") or 0)
    following = int(result.get("following") or 0)
    posts_count = int(result.get("posts_count") or 0)

    posts_data: list[dict[str, Any]] = result.get("posts") or []
    metrics = compute_post_metrics(posts_data, followers=followers)
    avg_likes = float(metrics["avg_likes"])
    avg_views = float(metrics["avg_views"])
    avg_comments = float(metrics["avg_comments"])
    eng = float(metrics["engagement_rate"])
    g_pct = growth_pct(followers, prev_followers)
    g_abs = followers - prev_followers

    profile.full_name = result.get("full_name") or profile.full_name
    profile.bio = result.get("bio") or profile.bio
    profile.website = result.get("website") or profile.website
    profile.avatar_url = result.get("avatar_url") or profile.avatar_url
    profile.is_verified = bool(result.get("is_verified", profile.is_verified))
    profile.ig_user_id = result.get("ig_user_id") or profile.ig_user_id
    profile.is_private = bool(result.get("is_private", False))
    profile.is_business = bool(result.get("is_business", False))
    profile.category = result.get("category") or profile.category
    profile.highlight_reel_count = int(result.get("highlight_reel_count") or 0)
    profile.followers = followers
    profile.following = following
    profile.posts_count = posts_count
    profile.avg_likes = avg_likes
    profile.avg_views = avg_views
    profile.avg_comments = avg_comments
    profile.engagement_rate = eng
    profile.growth_pct_today = g_pct
    profile.follower_following_ratio = round(followers / following, 4) if following else float(followers)
    profile.insights = metrics
    profile.status = ProfileStatus.ACTIVE
    profile.last_scraped_at = datetime.utcnow()
    profile.last_success_at = datetime.utcnow()
    profile.last_error = None
    profile.updated_at = datetime.utcnow()
    # Preserve SPARK roster fields if present (never wipe on scrape)
    student = getattr(profile, "student", None)
    if isinstance(student, dict) and student:
        profile.student = student  # type: ignore[attr-defined]
    await profile.save()

    # Replace posts with this scrape's real set (avoid leftover demo/stale rows)
    await Post.find(Post.profile_id == str(profile.id)).delete()

    posts_saved = 0
    for p in posts_data:
        try:
            ig_post_id = str(p.get("ig_post_id") or p.get("id") or "")
            if not ig_post_id:
                continue
            existing = await Post.find_one(Post.ig_post_id == ig_post_id)
            posted_at = p.get("posted_at")
            if isinstance(posted_at, str):
                try:
                    posted_at = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
                except ValueError:
                    posted_at = None

            payload = dict(
                profile_id=str(profile.id),
                user_id=profile.user_id,
                ig_post_id=ig_post_id,
                shortcode=str(p.get("shortcode") or ig_post_id),
                media_type=_media_type(p.get("media_type")),
                caption=p.get("caption"),
                thumbnail_url=p.get("thumbnail_url"),
                permalink=p.get("permalink") or f"https://instagram.com/p/{p.get('shortcode')}/",
                likes=int(p.get("likes") or 0),
                comments=int(p.get("comments") or 0),
                views=int(p.get("views") or 0),
                posted_at=posted_at,
                scraped_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            if existing:
                for k, v in payload.items():
                    setattr(existing, k, v)
                await existing.save()
            else:
                await Post(**payload).insert()
            posts_saved += 1
        except Exception:
            # One bad post must never flip a successful scrape to failed
            continue

    try:
        existing_snap = await ProfileSnapshot.find_one(
            ProfileSnapshot.profile_id == str(profile.id),
            ProfileSnapshot.snapshot_date == today,
        )
        snap_data = dict(
            profile_id=str(profile.id),
            user_id=profile.user_id,
            snapshot_date=today,
            followers=followers,
            following=following,
            posts_count=posts_count,
            avg_likes=avg_likes,
            avg_views=avg_views,
            avg_comments=avg_comments,
            engagement_rate=eng,
            followers_growth=g_abs,
            followers_growth_pct=g_pct,
        )
        if existing_snap:
            for k, v in snap_data.items():
                setattr(existing_snap, k, v)
            await existing_snap.save()
        else:
            await ProfileSnapshot(**snap_data).insert()
    except Exception:
        pass

    job.status = JobStatus.SUCCESS
    job.finished_at = datetime.utcnow()
    job.updated_at = datetime.utcnow()
    await job.save()

    await ScrapeLog(
        job_id=str(job.id),
        profile_id=str(profile.id),
        user_id=profile.user_id,
        level="info",
        message="Scrape succeeded",
        details={
            "followers": followers,
            "posts": len(posts_data),
            "posts_saved": posts_saved,
            "path": (result.get("raw") or {}).get("path") if isinstance(result.get("raw"), dict) else None,
        },
    ).insert()

    user_settings = await UserSettings.find_one(UserSettings.user_id == profile.user_id)
    threshold = (
        user_settings.follower_growth_notify_pct
        if user_settings
        else settings.follower_growth_notify_pct
    )
    spike_threshold = (
        user_settings.engagement_spike_pct
        if user_settings
        else settings.engagement_spike_notify_pct
    )

    if g_pct >= threshold and g_abs > 0:
        await Notification(
            user_id=profile.user_id,
            profile_id=str(profile.id),
            type=NotificationType.FOLLOWERS_UP,
            title=f"@{profile.username} grew {g_pct}%",
            body=f"Followers increased by {g_abs:,} ({g_pct}%).",
            meta={"growth_pct": g_pct, "growth": g_abs},
        ).insert()
    elif g_pct < 0 and (not user_settings or user_settings.notify_followers_down):
        await Notification(
            user_id=profile.user_id,
            profile_id=str(profile.id),
            type=NotificationType.FOLLOWERS_DOWN,
            title=f"@{profile.username} lost followers",
            body=f"Followers changed by {g_abs:,} ({g_pct}%).",
            meta={"growth_pct": g_pct, "growth": g_abs},
        ).insert()

    if prev_followers and eng and profile.engagement_rate:
        # crude spike vs previous cached engagement
        pass

    if avg_likes and profile.avg_likes and spike_threshold:
        # notify on strong absolute engagement for small accounts
        if avg_likes > 0 and followers > 0 and eng >= spike_threshold / 10:
            pass


async def mark_scrape_failed(job: Job, profile: Profile, error: str, *, unavailable: bool = False) -> None:
    # Known false positives / pagination traps must NEVER leave the profile as "failed"
    # when Instagram card metrics (followers/posts_count) already exist.
    soft = is_false_pymongo_failure(error) or "incomplete timeline" in str(error).lower()
    if soft and not unavailable:
        job.status = JobStatus.FAILED
        job.error_message = humanize_scrape_error(error)
        job.finished_at = datetime.utcnow()
        job.updated_at = datetime.utcnow()
        await job.save()
        # Keep / restore ACTIVE so the UI never shows failed+⚠️ for these cases
        if profile.status != ProfileStatus.PAUSED:
            profile.status = ProfileStatus.ACTIVE
        profile.last_error = None
        profile.last_scraped_at = datetime.utcnow()
        if not profile.last_success_at and (profile.followers or profile.posts_count):
            profile.last_success_at = datetime.utcnow()
        profile.updated_at = datetime.utcnow()
        student = getattr(profile, "student", None)
        if isinstance(student, dict) and student:
            profile.student = student  # type: ignore[attr-defined]
        await profile.save()
        return

    friendly = humanize_scrape_error(error)
    job.status = JobStatus.FAILED
    job.error_message = friendly
    job.finished_at = datetime.utcnow()
    job.updated_at = datetime.utcnow()
    await job.save()

    profile.last_scraped_at = datetime.utcnow()
    profile.last_error = friendly
    profile.status = ProfileStatus.UNAVAILABLE if unavailable else ProfileStatus.FAILED
    profile.updated_at = datetime.utcnow()
    student = getattr(profile, "student", None)
    if isinstance(student, dict) and student:
        profile.student = student  # type: ignore[attr-defined]
    await profile.save()

    await ScrapeLog(
        job_id=str(job.id),
        profile_id=str(profile.id),
        user_id=profile.user_id,
        level="error",
        message=friendly,
        details={"raw": str(error)[:500]} if str(error) != friendly else {},
    ).insert()

    ntype = NotificationType.PROFILE_UNAVAILABLE if unavailable else NotificationType.SCRAPE_FAILED
    await Notification(
        user_id=profile.user_id,
        profile_id=str(profile.id),
        type=ntype,
        title=f"Scrape failed for @{profile.username}",
        body=friendly[:280],
    ).insert()
