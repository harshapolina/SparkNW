"""Persist scrape results → profile, posts, snapshot, notifications."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from instascope_scraper.caps import caps_env
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

_POST_INSERT_CHUNK = 200


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


def _configured_max_posts() -> int:
    """0 means uncapped (full timeline). Reads active ScrapeCaps via caps_env."""
    raw = (caps_env("SCRAPE_MAX_POSTS", "0") or "0").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


def _is_complete_enough(posts_count: int, scraped: int, followers: int) -> bool:
    """Accept capped scrapes and first-pass samples so timeouts don't leave zeros."""
    # Instagram-reported empty timeline — card alone is enough.
    if posts_count == 0 and scraped == 0:
        return True

    if scraped <= 0 and followers <= 0:
        return False
    cap = _configured_max_posts()
    if cap > 0:
        target = min(posts_count, cap) if posts_count > 0 else cap
        # Hit the intentional cap (allow small shortfall).
        if scraped >= max(1, target - 2):
            return True
        # Useful first sample: card metrics + a page of posts.
        if followers > 0 and scraped >= min(12, target):
            return True
        return False

    # Full-timeline mode — still accept a strong partial rather than failing to zeros
    # when Instagram rate-limits mid-pagination (common on VPS / shared IPs).
    if followers > 0 and scraped >= 12:
        return True
    if posts_count > 0:
        need = posts_count if posts_count <= 12 else max(posts_count - 2, 1)
        return scraped >= need
    return scraped > 0 or followers > 0


def is_soft_scrape_failure(error: BaseException | str | None) -> bool:
    """True for non-fatal scrape issues that must not leave the profile badge as failed."""
    if error is None:
        return False
    low = str(error).lower()
    return (
        "incomplete timeline" in low
        or "refusing to save" in low
        or "pagination" in low
        or "still short" in low
        or "rate-limited" in low
        or "rate limited" in low
        or "please wait" in low
        or "timed out" in low
        or ("attribute" in low and "collection" in low)  # leftover AttributeError junk in DB
    )


def humanize_scrape_error(err: BaseException | str) -> str:
    """User-facing scrape failure text."""
    raw = str(err)
    low = raw.lower()
    if "err_tunnel" in low or "tunnel_connection" in low:
        return "Proxy tunnel failed opening Instagram. Check Decodo credentials, then Refresh."
    if "net::err_" in low or "page.goto" in low:
        return "Network error reaching Instagram via proxy. Refresh to retry (HTTP fallback enabled)."
    if "login wall" in low or ("login" in low and "blocked" in low):
        return "Instagram showed a login wall. Verify residential proxy session."
    if "could not extract" in low:
        return (
            "Instagram blocked this server IP. Wait a few minutes and Refresh, "
            "or configure SCRAPE_PROXY_URL (residential)."
        )
    if "rate-limited" in low or "rate limited" in low or "please wait" in low:
        return (
            "Instagram rate-limited this server. Wait a few minutes, then Refresh. "
            "A residential SCRAPE_PROXY_URL avoids this."
        )
    if "incomplete timeline" in low:
        return "Partial timeline only — Instagram blocked full pagination. Data may still be usable after Refresh."
    if "refusing to save" in low:
        return "Scrape was incomplete and was not saved over existing data. Please Refresh again."
    if "does not exist" in low or "doesn't exist" in low or "not found" in low:
        if "does not exist" in low or "doesn't exist" in low:
            return raw if len(raw) <= 220 else raw[:217] + "..."
        return "This Instagram profile does not exist."
    if len(raw) > 220:
        return raw[:217] + "..."
    return raw


async def heal_soft_scrape_failure(profile: Profile) -> bool:
    """Clear soft/stale failed status when the profile already has real card data."""
    status_val = profile.status.value if hasattr(profile.status, "value") else str(profile.status)
    if status_val != "failed":
        return False
    err = str(profile.last_error or "")
    soft = not err.strip() or is_soft_scrape_failure(err)
    has_card = bool(profile.followers or profile.posts_count or profile.last_success_at)
    # Also heal when Insights still shows first-card-only (~12) under a larger posts_count
    insights = profile.insights if isinstance(profile.insights, dict) else {}
    sampled = int(insights.get("sampled_posts") or 0)
    stale_partial = bool(profile.posts_count and sampled and sampled < profile.posts_count)
    if not ((soft or stale_partial) and has_card):
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

    # Login-wall / rate-limit scrapes often return full posts but followers=0.
    # Never wipe known card metrics with zeros when the timeline itself is good.
    if followers <= 0 and profile.followers > 0:
        followers = int(profile.followers)
    if following <= 0 and profile.following > 0:
        following = int(profile.following)
    if posts_count <= 0 and len(posts_data) > 0:
        posts_count = max(int(profile.posts_count or 0), len(posts_data))

    # NEVER wipe a good profile with an incomplete / empty scrape.
    # When SCRAPE_MAX_POSTS is capped (API inline/bulk), completeness is vs that cap.
    if not _is_complete_enough(posts_count, len(posts_data), followers):
        raise ValueError(
            f"Refusing to save incomplete scrape ({len(posts_data)}/{posts_count or '?'} posts)"
        )
    if posts_count > 0 and not posts_data and _configured_max_posts() <= 0:
        raise ValueError(
            f"Refusing to save empty scrape ({len(posts_data)}/{posts_count} posts)"
        )
    if followers <= 0 and posts_count <= 0 and not posts_data:
        raise ValueError("Refusing to save empty scrape result")

    metrics = compute_post_metrics(posts_data, followers=followers)
    # Guard: never replace real insights with an all-zero metrics blob
    if (
        int(metrics.get("sampled_posts") or 0) == 0
        and isinstance(profile.insights, dict)
        and int((profile.insights or {}).get("sampled_posts") or 0) > 0
    ):
        raise ValueError("Refusing to overwrite insights with empty metrics")

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
    prev_source = (getattr(profile, "scrape_progress", None) or {}).get("source")
    done_progress: dict[str, Any] = {
        "active": False,
        "phase": "done",
        "scraped_posts": len(posts_data),
        "total_posts": posts_count or len(posts_data),
        "posts_left": 0,
        "percent": 100,
    }
    if prev_source:
        done_progress["source"] = prev_source
    profile.scrape_progress = done_progress
    profile.updated_at = datetime.utcnow()
    # Preserve SPARK roster fields if present (never wipe on scrape)
    student = getattr(profile, "student", None)
    if isinstance(student, dict) and student:
        profile.student = student  # type: ignore[attr-defined]
    await profile.save()

    # Replace posts with this scrape's real set (avoid leftover demo/stale rows)
    await Post.find(Post.profile_id == str(profile.id)).delete()

    post_docs: list[Post] = []
    for p in posts_data:
        try:
            ig_post_id = str(p.get("ig_post_id") or p.get("id") or "")
            if not ig_post_id:
                continue
            posted_at = p.get("posted_at")
            if isinstance(posted_at, str):
                try:
                    posted_at = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
                except ValueError:
                    posted_at = None

            post_docs.append(
                Post(
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
            )
        except Exception:
            # One bad post must never flip a successful scrape to failed
            continue

    posts_saved = 0
    for i in range(0, len(post_docs), _POST_INSERT_CHUNK):
        chunk = post_docs[i : i + _POST_INSERT_CHUNK]
        try:
            await Post.insert_many(chunk)
            posts_saved += len(chunk)
        except Exception:
            for doc in chunk:
                try:
                    await doc.insert()
                    posts_saved += 1
                except Exception:
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
    # Soft failures must NEVER leave the profile badge as "failed" when card data exists.
    # But empty profiles must stay failed with a visible error — otherwise the UI shows
    # "Done — 0 followers · 0 posts" and looks like a successful empty scrape.
    has_card = bool(int(profile.followers or 0) or int(profile.posts_count or 0) or profile.last_success_at)
    if is_soft_scrape_failure(error) and not unavailable and has_card:
        job.status = JobStatus.FAILED
        job.error_message = humanize_scrape_error(error)
        job.finished_at = datetime.utcnow()
        job.updated_at = datetime.utcnow()
        await job.save()
        if profile.status != ProfileStatus.PAUSED:
            profile.status = ProfileStatus.ACTIVE
        # Keep a soft note so Refresh messaging is honest; do not pretend we scraped zeros.
        profile.last_error = humanize_scrape_error(error)
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

    # Only stamp last_scraped_at on hard failures when we already had data (attempt recorded).
    # For empty profiles, leave last_scraped_at alone so the UI does not show "Done".
    if has_card:
        profile.last_scraped_at = datetime.utcnow()
    profile.last_error = friendly
    profile.status = ProfileStatus.UNAVAILABLE if unavailable else ProfileStatus.FAILED
    # Always clear active scrape UI so bulk queue is not stuck "running".
    profile.scrape_progress = {
        "active": False,
        "phase": "unavailable" if unavailable else "failed",
        "scraped_posts": 0,
        "total_posts": int(profile.posts_count or 0),
        "posts_left": 0,
        "percent": 100,
        "source": (getattr(profile, "scrape_progress", None) or {}).get("source"),
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }
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
        details={"raw": str(error)[:500], "unavailable": unavailable}
        if str(error) != friendly or unavailable
        else {},
    ).insert()

    ntype = NotificationType.PROFILE_UNAVAILABLE if unavailable else NotificationType.SCRAPE_FAILED
    title = (
        f"@{profile.username} does not exist on Instagram"
        if unavailable
        else f"Scrape failed for @{profile.username}"
    )
    await Notification(
        user_id=profile.user_id,
        profile_id=str(profile.id),
        type=ntype,
        title=title,
        body=friendly[:280],
    ).insert()
