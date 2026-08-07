"""Real Instagram profile + posts scraping via Playwright.

No demo/fake data. Fails loudly if Instagram blocks or the profile is unavailable.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import traceback
from datetime import datetime, timezone
from typing import Any, Optional

from instascope_scraper.browser import browser_session
from instascope_scraper.caps import ScrapeCaps, caps_env, use_caps
from instascope_scraper.instagram_time import infer_posted_at_iso
from instascope_scraper.types import ProxyConfig, ScrapedPost, ScrapeResult, proxy_to_httpx_url

logger = logging.getLogger("instascope.scraper.profile")


class ScrapeError(Exception):
    def __init__(self, message: str, *, unavailable: bool = False):
        super().__init__(message)
        self.unavailable = unavailable


def _parse_count(raw: str | int | float | None) -> int:
    if raw is None:
        return 0
    if isinstance(raw, (int, float)):
        return int(raw)
    s = str(raw).replace(",", "").strip().upper()
    mult = 1
    if s.endswith("K"):
        mult = 1_000
        s = s[:-1]
    elif s.endswith("M"):
        mult = 1_000_000
        s = s[:-1]
    elif s.endswith("B"):
        mult = 1_000_000_000
        s = s[:-1]
    try:
        return int(float(s) * mult)
    except ValueError:
        return 0


def _media_type_from_node(node: dict[str, Any]) -> str:
    typename = (node.get("__typename") or node.get("product_type") or "").lower()
    mt = node.get("media_type")
    if mt == 8 or "sidecar" in typename or node.get("edge_sidecar_to_children") or node.get("carousel_media"):
        return "carousel"
    if (
        mt == 2
        or "video" in typename
        or node.get("is_video")
        or typename in {"clips", "reel", "reels"}
        or node.get("product_type") == "clips"
    ):
        if node.get("product_type") == "clips" or "reel" in typename:
            return "reel"
        return "video"
    return "image"


def _caption_from_node(node: dict[str, Any]) -> Optional[str]:
    edges = (
        (node.get("edge_media_to_caption") or {}).get("edges")
        or (node.get("caption") and [{"node": {"text": node.get("caption")}}])
        or []
    )
    if isinstance(node.get("caption"), dict):
        return node["caption"].get("text")
    if edges:
        return edges[0].get("node", {}).get("text")
    if isinstance(node.get("caption"), str):
        return node.get("caption")
    return None


def _views_from_mapping(obj: dict[str, Any] | None) -> int:
    """Pick the best play/view count from an IG media object.

    Instagram exposes several fields; public reel UI usually matches play_count.
    We take the MAX so we don't under-count when one field is stale/lower.
    """
    if not isinstance(obj, dict):
        return 0
    keys = (
        "play_count",
        "ig_play_count",
        "video_play_count",
        "video_view_count",
        "view_count",
        "fb_play_count",
        "play_count_disabled",  # ignore non-numeric below
    )
    best = 0
    for k in keys:
        if k == "play_count_disabled":
            continue
        best = max(best, _parse_count(obj.get(k)))
    # Nested shapes seen on feed / clips payloads
    for nest_key in ("clips_metadata", "media", "video_versions", "metrics"):
        nested = obj.get(nest_key)
        if isinstance(nested, dict):
            best = max(best, _views_from_mapping(nested))
    return best


def _post_from_node(node: dict[str, Any]) -> ScrapedPost | None:
    shortcode = node.get("shortcode") or node.get("code")
    post_id = str(node.get("id") or node.get("pk") or shortcode or "")
    if not shortcode and not post_id:
        return None
    shortcode = shortcode or post_id
    posted_at = None
    # Prefer normalized taken_at (handles ms clocks) then shortcode decode
    try:
        from instascope_scraper.http_profile import _node_taken_unix

        ts = _node_taken_unix(node)
        if ts is not None:
            posted_at = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except Exception:
        posted_at = None
    if not posted_at:
        posted_at = infer_posted_at_iso(
            shortcode=str(shortcode) if shortcode else None,
            ig_post_id=post_id or None,
        )

    likes = _parse_count(
        (node.get("edge_liked_by") or {}).get("count")
        or (node.get("edge_media_preview_like") or {}).get("count")
        or node.get("like_count")
        or node.get("likes")
    )
    comments = _parse_count(
        (node.get("edge_media_to_comment") or {}).get("count")
        or (node.get("edge_media_to_parent_comment") or {}).get("count")
        or node.get("comment_count")
        or node.get("comments")
    )
    views = _views_from_mapping(node)
    # Carousel: sum play counts from video slides when parent has none
    if views < 10:
        children = (
            (node.get("edge_sidecar_to_children") or {}).get("edges")
            or node.get("carousel_media")
            or []
        )
        child_views = 0
        for edge in children:
            child = edge.get("node") if isinstance(edge, dict) and "node" in edge else edge
            if not isinstance(child, dict):
                continue
            child_views += _views_from_mapping(child)
        if child_views > views:
            views = child_views

    thumb = (
        node.get("display_url")
        or node.get("thumbnail_src")
        or (node.get("image_versions2") or {}).get("candidates", [{}])[0].get("url")
    )
    media_type = _media_type_from_node(node)
    path = "reel" if media_type == "reel" else "p"
    return ScrapedPost(
        ig_post_id=post_id or shortcode,
        shortcode=shortcode,
        media_type=media_type,
        caption=_caption_from_node(node),
        thumbnail_url=thumb,
        permalink=f"https://www.instagram.com/{path}/{shortcode}/",
        likes=likes,
        comments=comments,
        views=views,
        posted_at=posted_at,
        is_video=bool(node.get("is_video") or media_type in {"video", "reel"} or views > 0),
        accessibility_caption=node.get("accessibility_caption"),
    )


def _user_from_web_profile(payload: dict[str, Any]) -> dict[str, Any] | None:
    user = payload.get("data", {}).get("user") if "data" in payload else payload.get("user")
    if not user and isinstance(payload.get("data"), dict):
        user = payload["data"]
    return user if isinstance(user, dict) else None


def _result_from_user(username: str, user: dict[str, Any], *, posts_override: list[ScrapedPost] | None = None) -> ScrapeResult:
    posts: list[ScrapedPost] = list(posts_override or [])
    if not posts:
        timeline = (
            (user.get("edge_owner_to_timeline_media") or {}).get("edges")
            or (user.get("edge_felix_video_timeline") or {}).get("edges")
            or []
        )
        for edge in timeline:
            node = edge.get("node") if isinstance(edge, dict) else None
            if not node and isinstance(edge, dict):
                node = edge
            if not isinstance(node, dict):
                continue
            post = _post_from_node(node)
            if post:
                posts.append(post)

        # Newer shape: user["media"]["nodes"] / "items"
        for key in ("media", "reel"):
            media = user.get(key) or {}
            for node in media.get("nodes") or media.get("items") or []:
                if isinstance(node, dict):
                    post = _post_from_node(node)
                    if post:
                        posts.append(post)

    # Dedupe by shortcode
    seen: set[str] = set()
    unique_posts: list[ScrapedPost] = []
    for p in posts:
        if p.shortcode in seen:
            continue
        seen.add(p.shortcode)
        unique_posts.append(p)

    followers = _parse_count(
        user.get("edge_followed_by", {}).get("count")
        if isinstance(user.get("edge_followed_by"), dict)
        else user.get("follower_count") or user.get("followers")
    )
    following = _parse_count(
        user.get("edge_follow", {}).get("count")
        if isinstance(user.get("edge_follow"), dict)
        else user.get("following_count") or user.get("following")
    )
    posts_count = _parse_count(
        user.get("edge_owner_to_timeline_media", {}).get("count")
        if isinstance(user.get("edge_owner_to_timeline_media"), dict)
        else user.get("media_count") or user.get("posts_count")
    )

    website = user.get("external_url") or user.get("website")
    bio = user.get("biography") or user.get("bio")
    avatar = (
        user.get("profile_pic_url_hd")
        or user.get("profile_pic_url")
        or user.get("hd_profile_pic_url_info", {}).get("url")
    )

    return ScrapeResult(
        username=user.get("username") or username,
        ig_user_id=str(user.get("id") or user.get("pk") or "") or None,
        full_name=user.get("full_name") or user.get("fullName"),
        bio=bio,
        website=website,
        avatar_url=avatar,
        is_verified=bool(user.get("is_verified")),
        followers=followers,
        following=following,
        posts_count=posts_count,
        posts=unique_posts,
        is_private=bool(user.get("is_private")),
        is_business=bool(user.get("is_business_account") or user.get("is_professional_account")),
        category=user.get("category_name") or user.get("business_category_name"),
        pronouns=(
            (user.get("pronouns") or [None])[0]
            if isinstance(user.get("pronouns"), list) and user.get("pronouns")
            else (user.get("pronouns") if isinstance(user.get("pronouns"), str) else None)
        ),
        highlight_reel_count=_parse_count(user.get("highlight_reel_count")),
        raw={"source": "web_profile_info", "posts_scraped": len(unique_posts)},
    )


def _expected_posts_count(user: dict[str, Any]) -> int:
    return _parse_count(
        user.get("edge_owner_to_timeline_media", {}).get("count")
        if isinstance(user.get("edge_owner_to_timeline_media"), dict)
        else user.get("media_count") or user.get("posts_count")
    )


def _posts_count_known(user: dict[str, Any] | None) -> bool:
    """True when Instagram included an explicit media/posts count (including 0)."""
    if not isinstance(user, dict):
        return False
    for key in ("media_count", "posts_count", "total_clips_count"):
        if user.get(key) is not None:
            return True
    edge = user.get("edge_owner_to_timeline_media")
    if isinstance(edge, dict) and edge.get("count") is not None:
        return True
    return False


def _posts_complete(
    posts: list[ScrapedPost],
    posts_count: int,
    *,
    hit_cohort_floor: bool = False,
    feed_exhausted: bool = False,
) -> bool:
    """True when we've collected enough posts for the active scrape caps.

    Respects SCRAPE_MAX_POSTS / ScrapeCaps.max_posts so a capped bulk pass
    (e.g. 48 of 3000) is treated as complete.

    When ``hit_cohort_floor`` is True we already walked newest→oldest down to
    SPARK_COHORT_START (2026-07-15) — that is a complete programme scrape even
    if Instagram's lifetime ``posts_count`` is much larger.

    When cohort stop is on, do **not** treat a first-page sample as complete
    just because SCRAPE_MAX_POSTS / lifetime math looks satisfied — we must
    reach the Jul 15 floor or exhaust the feed *and* have essentially all
    lifetime posts (account only posted inside the programme window).

    posts_count == 0 with no posts means a confirmed-empty timeline (callers
    must only set posts_count=0 when Instagram explicitly reported it).
    """
    # Programme window complete — do not chase lifetime posts_count.
    if hit_cohort_floor:
        return True

    # Confirmed empty account: nothing to fetch.
    if posts_count == 0:
        return len(posts) == 0

    # Cohort mode: first-page (~12) is never "done" unless we hit Jul 15.
    # Feed exhaustion alone is only complete when collected ≈ lifetime total
    # (no older posts exist). Stalled pagination on a 166-post account must
    # NOT look finished after 9 posts.
    try:
        from instascope_scraper.http_profile import _cohort_floor_unix

        if _cohort_floor_unix() is not None:
            if feed_exhausted:
                got = len(posts)
                if posts_count <= 12:
                    return got >= posts_count
                return got >= max(posts_count - 2, 1)
            return False
    except Exception:
        pass

    if not posts:
        return False
    got = len(posts)
    try:
        cap = int((caps_env("SCRAPE_MAX_POSTS", "0") or "0").strip() or "0")
    except ValueError:
        cap = 0
    if cap > 0:
        target = min(posts_count, cap)
        if target <= 12:
            return got >= target
        return got >= max(target - 2, 1)

    # Small accounts: every post must be present (6→2 / 1→0 must NOT pass).
    if posts_count <= 12:
        return got >= posts_count
    # Large accounts: allow 1–2 deleted/hidden drift.
    return got >= max(posts_count - 2, 1)


def _result_feed_exhausted(result: ScrapeResult | None) -> bool:
    if not result or not isinstance(result.raw, dict):
        return False
    return bool(result.raw.get("feed_exhausted"))


def _result_hit_cohort_floor(result: ScrapeResult | None) -> bool:
    if not result or not isinstance(result.raw, dict):
        return False
    return bool(result.raw.get("hit_cohort_floor"))


def _mark_cohort_floor(result: ScrapeResult, hit: bool = True) -> ScrapeResult:
    if hit:
        result.raw = {**(result.raw or {}), "hit_cohort_floor": True}
    return result


def _useful_partial(result: ScrapeResult) -> bool:
    """Card + a real sample — save instead of failing large accounts mid-pagination."""
    if result.is_private:
        return True
    if _result_hit_cohort_floor(result):
        return True
    if _result_feed_exhausted(result):
        # Cohort mode: stalled first-page exhaustion on a large account is NOT
        # a useful complete scrape — saving it would wipe missing in-window posts.
        try:
            from instascope_scraper.http_profile import _cohort_floor_unix

            if _cohort_floor_unix() is not None:
                pc = int(result.posts_count or 0)
                got = len(result.posts)
                if pc > 12 and got < max(1, pc - 2):
                    return False
        except Exception:
            pass
        return True
    # Confirmed empty public profile with a card is a finished scrape.
    if int(result.posts_count or 0) == 0 and len(result.posts) == 0 and int(result.followers or 0) > 0:
        return True
    # Cohort programme scrapes must reach Jul 15 — never accept first-page-only.
    try:
        from instascope_scraper.http_profile import _cohort_floor_unix

        if _cohort_floor_unix() is not None:
            return False
    except Exception:
        pass
    got = len(result.posts)
    if int(result.followers or 0) > 0 and got >= 12:
        return True
    if got >= 48 and int(result.posts_count or 0) > 0:
        return True
    return False


def _raise_if_incomplete(result: ScrapeResult) -> None:
    """Raise only when the timeline is useless; accept capped / strong partials."""
    if result.is_private:
        return
    if _posts_complete(
        result.posts,
        result.posts_count,
        hit_cohort_floor=_result_hit_cohort_floor(result),
        feed_exhausted=_result_feed_exhausted(result),
    ):
        return
    strict = (caps_env("SCRAPE_STRICT", "0") or "0").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    if not strict and _useful_partial(result):
        logger.warning(
            "accepting partial timeline @%s posts=%s/%s followers=%s (non-strict)",
            result.username,
            len(result.posts),
            result.posts_count,
            result.followers,
        )
        return
    got = len(result.posts)
    expected = result.posts_count
    raise ScrapeError(
        f"Incomplete timeline: only {got}/{expected} posts "
        f"(Instagram pagination blocked). Check SCRAPE_PROXY_URL / Decodo."
    )


def _posts_from_nodes(nodes: list[dict[str, Any]]) -> list[ScrapedPost]:
    posts: list[ScrapedPost] = []
    seen: set[str] = set()
    floor: int | None = None
    try:
        from instascope_scraper.http_profile import _cohort_floor_unix

        floor = _cohort_floor_unix()
    except Exception:
        floor = None
    for node in nodes:
        post = _post_from_node(node)
        if not post or post.shortcode in seen:
            continue
        if floor is not None and post.posted_at:
            try:
                ts = int(datetime.fromisoformat(post.posted_at.replace("Z", "+00:00")).timestamp())
                if ts < floor:
                    continue
            except ValueError:
                pass
        seen.add(post.shortcode)
        posts.append(post)
    return posts


def _merge_posts(base: list[ScrapedPost], extra: list[ScrapedPost]) -> list[ScrapedPost]:
    """Union by shortcode, keeping the stronger engagement numbers.

    Seeds from web_profile often have weak/zero play_count; feed rows for the
    same reel carry the real count. Dropping duplicates used to lock in ~half
    the true total reel views.
    """
    by_code: dict[str, ScrapedPost] = {}
    order: list[str] = []

    def _keep(p: ScrapedPost) -> None:
        code = str(p.shortcode or "")
        if not code:
            return
        prev = by_code.get(code)
        if prev is None:
            by_code[code] = p
            order.append(code)
            return
        by_code[code] = ScrapedPost(
            ig_post_id=prev.ig_post_id or p.ig_post_id,
            shortcode=code,
            media_type=p.media_type or prev.media_type,
            caption=p.caption if p.caption not in (None, "") else prev.caption,
            thumbnail_url=p.thumbnail_url or prev.thumbnail_url,
            permalink=p.permalink or prev.permalink,
            likes=max(int(prev.likes or 0), int(p.likes or 0)),
            comments=max(int(prev.comments or 0), int(p.comments or 0)),
            views=max(int(prev.views or 0), int(p.views or 0)),
            posted_at=prev.posted_at or p.posted_at,
            is_video=bool(prev.is_video or p.is_video),
            accessibility_caption=p.accessibility_caption or prev.accessibility_caption,
        )

    for p in base:
        _keep(p)
    for p in extra:
        _keep(p)
    return [by_code[c] for c in order]


async def _emit_progress(on_progress, **payload: Any) -> None:
    if not on_progress:
        return
    try:
        res = on_progress(payload)
        if asyncio.iscoroutine(res):
            await res
    except Exception:
        logger.exception("on_progress callback failed")


async def _expand_all_posts(
    username: str,
    user: dict[str, Any],
    *,
    proxy_url: str | None,
    on_progress=None,
) -> tuple[list[ScrapedPost], bool]:
    """Paginate newest-first until cohort floor (Jul 15 2026) or posts_count.

    Returns ``(posts, hit_cohort_floor)``. Hitting the programme floor is success —
    we intentionally ignore older lifetime posts.
    """
    from instascope_scraper.http_profile import _timeline_from_user, fetch_all_media_nodes

    user_id = str(user.get("id") or user.get("pk") or "")
    if not user_id:
        logger.warning("expand @%s: missing user_id — returning card edges only", username)
        return _result_from_user(username, user).posts, False

    expected = _expected_posts_count(user)
    initial_nodes, cursor, has_next = _timeline_from_user(user)
    posts = _posts_from_nodes(initial_nodes)
    hit_cohort_floor = False
    await _emit_progress(
        on_progress,
        phase="timeline",
        scraped_posts=len(posts),
        total_posts=expected,
    )
    logger.info(
        "expand @%s start expected=%s initial=%s has_next=%s cursor=%s proxy=%s",
        username,
        expected,
        len(posts),
        has_next,
        (cursor or "")[:48],
        bool(proxy_url),
    )

    # Instagram says 0 posts — do not paginate / rotate proxies for an empty grid.
    # Only when the count field is present (missing count ≠ empty account).
    if expected == 0 and _posts_count_known(user):
        logger.info("expand @%s expected=0 — empty timeline, skipping pagination", username)
        return posts, False
    if expected == 0 and not _posts_count_known(user):
        logger.warning(
            "expand @%s posts_count unknown — will paginate until feed ends/stagnant",
            username,
        )

    def _seed_nodes_from_posts(items: list[ScrapedPost]) -> list[dict[str, Any]]:
        """Re-seed pagination from posts we already have (continue past page 1).

        Must include timestamps — undated seeds were treated as a cohort-floor hit
        and stopped pagination after the first ~12 posts.
        """
        seed: list[dict[str, Any]] = []
        for p in items:
            node: dict[str, Any] = {
                "code": p.shortcode,
                "shortcode": p.shortcode,
                "id": p.ig_post_id,
                "pk": p.ig_post_id,
            }
            if p.posted_at:
                try:
                    ts = int(
                        datetime.fromisoformat(p.posted_at.replace("Z", "+00:00")).timestamp()
                    )
                    node["taken_at"] = ts
                    node["taken_at_timestamp"] = ts
                except ValueError:
                    pass
            seed.append(node)
        return seed

    # Keep going until cohort floor or posts_count (or exhaust rounds).
    # Rotate residential proxies so one rate-limited port doesn't stall pagination.
    rounds = max(1, int(os.getenv("SCRAPE_EXPAND_ROUNDS") or "8"))
    from instascope_scraper.proxy_pool import all_proxy_httpx_urls

    pool_urls = all_proxy_httpx_urls()
    proxy_cycle: list[str | None] = []
    if proxy_url:
        proxy_cycle.append(proxy_url)
    for u in pool_urls:
        if u not in proxy_cycle:
            proxy_cycle.append(u)
    if not proxy_cycle:
        proxy_cycle = [None]
    if os.getenv("SCRAPE_DIRECT_FALLBACK", "1") != "0" and None not in proxy_cycle:
        proxy_cycle.append(None)

    stagnant_rounds = 0
    for round_i in range(rounds):
        if hit_cohort_floor or _posts_complete(
            posts, expected, hit_cohort_floor=hit_cohort_floor
        ):
            break
        if expected <= 0 and len(posts) > 12:
            break

        progressed = False
        for pxy in proxy_cycle:
            if hit_cohort_floor or _posts_complete(
                posts, expected, hit_cohort_floor=hit_cohort_floor
            ):
                break
            try:
                seed = initial_nodes if (round_i == 0 and not posts) else _seed_nodes_from_posts(posts)
                # Always ask for more while short of Instagram's count
                force_next = expected > len(posts) or (expected <= 0 and len(posts) <= 12)
                all_nodes, floor_hit = await fetch_all_media_nodes(
                    username,
                    user_id=user_id,
                    initial_nodes=seed,
                    initial_cursor=cursor if round_i == 0 else None,
                    initial_has_next=True if force_next else has_next,
                    expected_count=expected,
                    proxy=pxy,
                )
                if floor_hit:
                    hit_cohort_floor = True
                before = len(posts)
                posts = _merge_posts(posts, _posts_from_nodes(all_nodes))
                logger.info(
                    "expand @%s round=%s proxy=%s before=%s after=%s expected=%s cohort_floor=%s",
                    username,
                    round_i,
                    bool(pxy),
                    before,
                    len(posts),
                    expected,
                    hit_cohort_floor,
                )
                if hit_cohort_floor:
                    await _emit_progress(
                        on_progress,
                        phase="timeline",
                        scraped_posts=len(posts),
                        total_posts=expected,
                    )
                    logger.info(
                        "expand @%s cohort-complete posts=%s (lifetime expected=%s)",
                        username,
                        len(posts),
                        expected,
                    )
                    # Skip further proxy/round loops — programme window is done.
                    break
                if len(posts) > before:
                    progressed = True
                    stagnant_rounds = 0
                    cursor = None  # resume via seed from posts; avoid full re-page from start
                    await _emit_progress(
                        on_progress,
                        phase="timeline",
                        scraped_posts=len(posts),
                        total_posts=expected,
                    )
                else:
                    # Fail-fast when this proxy adds nothing — rotate, don't re-walk forever.
                    stagnant_rounds += 1
                    if stagnant_rounds >= 2:
                        logger.warning(
                            "expand @%s stagnant on proxy — rotate/retry posts=%s/%s cohort_floor=%s",
                            username,
                            len(posts),
                            expected,
                            hit_cohort_floor,
                        )
                        break  # next round / proxy — do NOT mark programme complete
            except Exception as exc:
                msg = str(exc).lower()
                if "please wait" in msg or "rate" in msg:
                    logger.warning("expand @%s please-wait on proxy — rotate", username)
                    continue
                logger.exception(
                    "expand @%s round=%s proxy=%s FAILED",
                    username,
                    round_i,
                    bool(pxy),
                )
                continue

        if hit_cohort_floor or _posts_complete(
            posts, expected, hit_cohort_floor=hit_cohort_floor
        ):
            break
        if progressed:
            stagnant_rounds = 0
        else:
            stagnant_rounds += 1
            # Keep trying a few no-progress rounds — IG often needs a fresh session
            if stagnant_rounds >= 3 and round_i >= 2:
                logger.warning(
                    "expand @%s giving up after stagnant_rounds=%s collected=%s/%s",
                    username,
                    stagnant_rounds,
                    len(posts),
                    expected,
                )
                break
        await asyncio.sleep(0.8 + round_i * 0.6)

    # HTTP media-info pass for reel play counts (before browser enrich)
    try:
        await _emit_progress(
            on_progress,
            phase="enriching",
            scraped_posts=len(posts),
            total_posts=expected or len(posts),
        )
        posts = await _enrich_views_via_http(posts, username=username, proxy_url=proxy_url)
    except Exception:
        logger.exception("expand @%s view enrich failed", username)

    logger.info(
        "expand @%s done collected=%s expected=%s cohort_floor=%s",
        username,
        len(posts),
        expected,
        hit_cohort_floor,
    )
    await _emit_progress(
        on_progress,
        phase="timeline",
        scraped_posts=len(posts),
        total_posts=expected or len(posts),
    )
    return posts, hit_cohort_floor


async def _enrich_views_via_http(
    posts: list[ScrapedPost],
    *,
    username: str,
    proxy_url: str | None,
) -> list[ScrapedPost]:
    """Fill reel play counts via /api/v1/media/{id}/info/ over HTTP+proxy."""
    import httpx
    from instascope_scraper.http_profile import _apply_csrf, _bootstrap_session, _client_headers

    # Always refresh reel play counts via media-info when possible. Feed/card
    # seeds can look "good enough" yet still be far below the public UI count.
    delay = float(os.getenv("SCRAPE_ENRICH_DELAY_SECONDS") or "0.5")
    targets = [
        p
        for p in posts
        if (p.media_type in {"reel", "video"} or p.is_video) and p.ig_post_id
    ]
    if not targets:
        return posts

    headers = _client_headers(username)
    timeout = httpx.Timeout(30.0)
    by_code = {p.shortcode: p for p in posts}

    async with httpx.AsyncClient(headers=headers, follow_redirects=True, proxy=proxy_url, timeout=timeout) as client:
        await _bootstrap_session(client, username)
        for post in targets:
            await asyncio.sleep(delay)
            media_id = str(post.ig_post_id).split("_")[0]
            url = f"https://www.instagram.com/api/v1/media/{media_id}/info/"
            req_headers = _client_headers(username)
            _apply_csrf(client, req_headers)
            try:
                res = await client.get(url, headers=req_headers)
                if res.status_code != 200:
                    continue
                payload = res.json()
            except Exception:
                continue
            items = payload.get("items") if isinstance(payload, dict) else None
            if not isinstance(items, list):
                continue
            best = post.views
            for it in items:
                if isinstance(it, dict):
                    best = max(best, _views_from_mapping(it))
            if best > post.views:
                updated = ScrapedPost(
                    ig_post_id=post.ig_post_id,
                    shortcode=post.shortcode,
                    media_type=post.media_type,
                    caption=post.caption,
                    thumbnail_url=post.thumbnail_url,
                    permalink=post.permalink,
                    likes=post.likes,
                    comments=post.comments,
                    views=best,
                    posted_at=post.posted_at,
                    is_video=post.is_video,
                    accessibility_caption=post.accessibility_caption,
                )
                by_code[post.shortcode] = updated

    return [by_code.get(p.shortcode, p) for p in posts]


def _enrich_limit(total_posts: int) -> int:
    """How many posts to open for missing likes/comments/views. 0 = all."""
    raw = (caps_env("SCRAPE_ENRICH_MAX", "0") or "0").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 0
    if n <= 0:
        return total_posts
    return min(n, total_posts)



def _result_from_meta(username: str, *, meta_desc: str | None, og_image: str | None, og_title: str | None) -> ScrapeResult | None:
    if not meta_desc and not og_title:
        return None
    followers = following = posts_count = 0
    if meta_desc:
        m = re.search(r"([\d.,]+[KMB]?)\s+Followers", meta_desc, flags=re.I)
        if m:
            followers = _parse_count(m.group(1))
        m = re.search(r"([\d.,]+[KMB]?)\s+Following", meta_desc, flags=re.I)
        if m:
            following = _parse_count(m.group(1))
        m = re.search(r"([\d.,]+[KMB]?)\s+Posts", meta_desc, flags=re.I)
        if m:
            posts_count = _parse_count(m.group(1))
    full_name = None
    if og_title:
        full_name = og_title.split("(")[0].strip() or None
        # Strip trailing "• Instagram photos and videos"
        if full_name and "instagram" in full_name.lower():
            full_name = re.split(r"\s*[•|]\s*", full_name)[0].strip()
    if followers == 0 and posts_count == 0 and not full_name and not og_image:
        return None
    return ScrapeResult(
        username=username,
        ig_user_id=None,
        full_name=full_name,
        bio=meta_desc,
        website=None,
        avatar_url=og_image,
        is_verified=False,
        followers=followers,
        following=following,
        posts_count=posts_count,
        posts=[],
        raw={"source": "meta_tags"},
    )


async def _try_private_from_html(
    username: str, *, proxy_url: str | None
) -> ScrapeResult | None:
    """When API card is blocked, detect private accounts from the public HTML page."""
    try:
        from instascope_scraper.http_profile import InstagramUserNotFound, fetch_profile_meta_card

        meta = await fetch_profile_meta_card(username, proxy=proxy_url)
    except InstagramUserNotFound:
        raise
    except Exception:
        logger.exception("private html probe @%s failed", username)
        return None
    if not meta or not meta.get("is_private"):
        return None
    card = _result_from_meta(
        username,
        meta_desc=meta.get("meta_desc"),
        og_image=meta.get("og_image"),
        og_title=meta.get("og_title"),
    )
    if card:
        card.is_private = True
        logger.info(
            "html_private @%s followers=%s posts=%s — saving private card",
            username,
            card.followers,
            card.posts_count,
        )
        return _finalize_result(card, path="html_private")
    logger.info("html_private @%s — private page with no meta counts", username)
    return _finalize_result(
        ScrapeResult(
            username=username,
            ig_user_id=None,
            full_name=None,
            bio=None,
            website=None,
            avatar_url=meta.get("og_image"),
            is_verified=False,
            followers=0,
            following=0,
            posts_count=0,
            posts=[],
            is_private=True,
            raw={"source": "html_private"},
        ),
        path="html_private",
    )


async def _fetch_web_profile_info(page, username: str) -> dict[str, Any] | None:
    """Call Instagram's public web_profile_info endpoint inside the browser context."""
    try:
        data = await page.evaluate(
            """async (username) => {
              const res = await fetch(
                `https://www.instagram.com/api/v1/users/web_profile_info/?username=${encodeURIComponent(username)}`,
                {
                  headers: {
                    'X-IG-App-ID': '936619743392459',
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': '*/*',
                  },
                  credentials: 'include',
                }
              );
              if (!res.ok) return { __error: res.status, __text: await res.text() };
              return await res.json();
            }""",
            username,
        )
        if isinstance(data, dict) and not data.get("__error"):
            return data
    except Exception:
        return None
    return None


async def _extract_posts_from_dom(page) -> list[ScrapedPost]:
    """Collect visible grid posts (links + images) when JSON API is thin."""
    items = await page.evaluate(
        """() => {
          const anchors = Array.from(document.querySelectorAll('a[href*="/p/"], a[href*="/reel/"]'));
          const out = [];
          const seen = new Set();
          for (const a of anchors) {
            const href = a.getAttribute('href') || '';
            const m = href.match(/\\/(p|reel)\\/([^\\/]+)/);
            if (!m) continue;
            const shortcode = m[2];
            if (seen.has(shortcode)) continue;
            seen.add(shortcode);
            const img = a.querySelector('img');
            out.push({
              shortcode,
              kind: m[1],
              thumbnail_url: img ? img.src : null,
              alt: img ? img.alt : null,
            });
            if (out.length >= 5000) break;
          }
          return out;
        }"""
    )
    posts: list[ScrapedPost] = []
    for item in items or []:
        shortcode = item.get("shortcode")
        if not shortcode:
            continue
        kind = item.get("kind") or "p"
        posted_at = infer_posted_at_iso(shortcode=str(shortcode), ig_post_id=str(shortcode))
        posts.append(
            ScrapedPost(
                ig_post_id=shortcode,
                shortcode=shortcode,
                media_type="reel" if kind == "reel" else "image",
                caption=item.get("alt"),
                thumbnail_url=item.get("thumbnail_url"),
                permalink=f"https://www.instagram.com/{'reel' if kind == 'reel' else 'p'}/{shortcode}/",
                likes=0,
                comments=0,
                views=0,
                posted_at=posted_at,
            )
        )
    return posts


async def _enrich_posts(page, posts: list[ScrapedPost], *, limit: int | None = None) -> list[ScrapedPost]:
    """Open individual post/reel pages to fill likes/comments/views.

    Reels always get a view/play-count pass when views look missing or weak,
    because feed payloads often under-report play_count vs the public UI.
    """
    if limit is None:
        limit = _enrich_limit(len(posts))
    delay = float(os.getenv("SCRAPE_ENRICH_DELAY_SECONDS") or "0.9")
    # Reels always re-check play counts — card/feed seeds under-report vs public UI.
    weak_views = int(os.getenv("SCRAPE_WEAK_VIEWS_THRESHOLD") or "1000")
    enriched: list[ScrapedPost] = []
    visited = 0

    for post in posts:
        is_reelish = post.media_type in {"reel", "video"} or post.is_video
        needs_views = bool(is_reelish)
        needs_eng = post.likes == 0 and post.comments == 0
        if visited >= limit:
            enriched.append(post)
            continue
        if not needs_views and not needs_eng:
            enriched.append(post)
            continue
        if (not needs_views) and post.views >= weak_views and (post.likes or post.comments):
            enriched.append(post)
            continue

        visited += 1
        try:
            resp = await page.goto(post.permalink, wait_until="domcontentloaded", timeout=45_000)
            await asyncio.sleep(delay)
            if resp and resp.status == 404:
                enriched.append(post)
                continue

            likes = comments = views = 0
            meta = await page.locator('meta[name="description"]').get_attribute("content")
            if meta:
                lm = re.search(r"([\d.,]+[KMB]?)\s+Likes?", meta, flags=re.I)
                cm = re.search(r"([\d.,]+[KMB]?)\s+Comments?", meta, flags=re.I)
                # "95.1K views" / "167,000 plays" / "167K plays"
                vm = re.search(
                    r"([\d.,]+[KMB]?)\s+(?:views?|plays?|video views?)",
                    meta,
                    flags=re.I,
                )
                if lm:
                    likes = _parse_count(lm.group(1))
                if cm:
                    comments = _parse_count(cm.group(1))
                if vm:
                    views = _parse_count(vm.group(1))

            # Pull play_count from embedded JSON / media info API (most accurate for reels)
            try:
                extracted = await page.evaluate(
                    """async ({ shortcode, mediaId }) => {
                      const pick = (obj) => {
                        if (!obj || typeof obj !== 'object') return 0;
                        const keys = ['play_count','ig_play_count','video_play_count','video_view_count','view_count'];
                        let best = 0;
                        for (const k of keys) {
                          const n = Number(obj[k]);
                          if (Number.isFinite(n) && n > best) best = n;
                        }
                        return best;
                      };
                      let best = 0;
                      // 1) media info by pk
                      if (mediaId) {
                        try {
                          const res = await fetch(`/api/v1/media/${mediaId}/info/`, {
                            credentials: 'include',
                            headers: { 'X-IG-App-ID': '936619743392459', 'X-Requested-With': 'XMLHttpRequest' },
                          });
                          if (res.ok) {
                            const json = await res.json();
                            const items = json.items || [];
                            for (const it of items) best = Math.max(best, pick(it));
                          }
                        } catch (e) {}
                      }
                      // 2) scan script tags for play_count near shortcode
                      try {
                        const scripts = Array.from(document.querySelectorAll('script'));
                        const re = /"play_count"\\s*:\\s*(\\d+)/g;
                        for (const s of scripts) {
                          const t = s.textContent || '';
                          if (shortcode && !t.includes(shortcode) && !t.includes('play_count')) continue;
                          let m;
                          while ((m = re.exec(t)) !== null) {
                            const n = Number(m[1]);
                            if (n > best) best = n;
                          }
                          const re2 = /"video_view_count"\\s*:\\s*(\\d+)/g;
                          while ((m = re2.exec(t)) !== null) {
                            const n = Number(m[1]);
                            if (n > best) best = n;
                          }
                        }
                      } catch (e) {}
                      // 3) visible "X views" / "X plays" text
                      try {
                        const body = document.body ? document.body.innerText : '';
                        const m = body.match(/([\\d.,]+\\s*[KMB]?)\\s+(views|plays)/i);
                        if (m) {
                          const raw = m[1].replace(/,/g, '').trim().toUpperCase();
                          let mult = 1;
                          let num = raw;
                          if (raw.endsWith('K')) { mult = 1e3; num = raw.slice(0, -1); }
                          else if (raw.endsWith('M')) { mult = 1e6; num = raw.slice(0, -1); }
                          else if (raw.endsWith('B')) { mult = 1e9; num = raw.slice(0, -1); }
                          const n = Math.round(parseFloat(num) * mult);
                          if (Number.isFinite(n) && n > best) best = n;
                        }
                      } catch (e) {}
                      return best;
                    }""",
                    {"shortcode": post.shortcode, "mediaId": post.ig_post_id},
                )
                if isinstance(extracted, (int, float)) and int(extracted) > views:
                    views = int(extracted)
            except Exception:
                pass

            og_image = await page.locator('meta[property="og:image"]').get_attribute("content")
            enriched.append(
                ScrapedPost(
                    ig_post_id=post.ig_post_id,
                    shortcode=post.shortcode,
                    media_type=post.media_type,
                    caption=post.caption
                    or (meta.split("-", 1)[-1].strip() if meta and "-" in meta else post.caption),
                    thumbnail_url=og_image or post.thumbnail_url,
                    permalink=post.permalink,
                    likes=likes or post.likes,
                    comments=comments or post.comments,
                    # Never downgrade a better feed view count
                    views=max(views, post.views),
                    posted_at=post.posted_at,
                    is_video=post.is_video,
                    accessibility_caption=post.accessibility_caption,
                )
            )
        except Exception:
            enriched.append(post)
    return enriched


async def _scroll_collect_all_posts(page, *, posts_count: int, existing: list[ScrapedPost], username: str = "") -> list[ScrapedPost]:
    """Infinite-scroll the profile grid until all public posts are visible in the DOM.

    Stop ONLY when ALL of these are true for consecutive stagnant scrolls:
      - no new posts
      - page height unchanged
      - no new GraphQL/feed network requests
      - no new DOM nodes
    Never stop merely because 12 posts exist.
    Empty accounts (posts_count == 0) return immediately.
    """
    from instascope_scraper.http_profile import _max_posts

    if posts_count == 0:
        logger.info("scroll @%s posts_count=0 — skipping grid scroll", username or "?")
        return list(existing)

    hard_cap = _max_posts()
    target = min(posts_count if posts_count > 0 else hard_cap, hard_cap)
    merged = list(existing)
    seen = {p.shortcode for p in merged}
    scroll_delay = float(os.getenv("SCRAPE_SCROLL_DELAY_SECONDS") or "1.1")
    # ~12 posts per scroll batch; allow plenty of room for slow lazy-loads
    max_scrolls = max(80, (target // 2) + 40)
    # Require several fully-idle scrolls before declaring end-of-feed
    idle_needed = max(3, int(os.getenv("SCRAPE_SCROLL_IDLE_STREAK") or "5"))
    idle_streak = 0

    net_feed = {"count": 0}
    net_gql = {"count": 0}

    def _on_request(req) -> None:
        u = req.url or ""
        if "/api/v1/feed/user/" in u:
            net_feed["count"] += 1
        elif "graphql" in u:
            net_gql["count"] += 1

    page.on("request", _on_request)

    async def _dom_stats() -> dict[str, int]:
        return await page.evaluate(
            """() => {
              const anchors = Array.from(document.querySelectorAll('a[href*="/p/"], a[href*="/reel/"]'));
              const seen = new Set();
              for (const a of anchors) {
                const m = (a.getAttribute('href') || '').match(/\\/(p|reel)\\/([^\\/]+)/);
                if (m) seen.add(m[2]);
              }
              const h = Math.max(
                document.body ? document.body.scrollHeight : 0,
                document.documentElement ? document.documentElement.scrollHeight : 0
              );
              return {
                posts: seen.size,
                height: h,
                nodes: document.querySelectorAll('*').length,
                locator: anchors.length,
              };
            }"""
        )

    logger.info(
        "scroll @%s start existing=%s target=%s max_scrolls=%s idle_needed=%s",
        username,
        len(merged),
        target,
        max_scrolls,
        idle_needed,
    )

    try:
        for i in range(max_scrolls):
            if target > 0 and len(merged) >= target:
                logger.info("scroll @%s reached target=%s collected=%s", username, target, len(merged))
                break

            before_posts = len(merged)
            before_feed = net_feed["count"]
            before_gql = net_gql["count"]
            before_stats = await _dom_stats()

            await page.evaluate(
                """(step) => {
                  const h = Math.max(
                    document.body.scrollHeight,
                    document.documentElement.scrollHeight
                  );
                  window.scrollTo(0, Math.min(h, (step + 1) * (window.innerHeight * 0.9)));
                  if (step % 3 === 2) window.scrollTo(0, h);
                }""",
                i,
            )
            await asyncio.sleep(scroll_delay)

            # Dismiss "See more" / load-more style buttons if present
            try:
                for label in ("See more", "Show more", "Load more"):
                    btn = page.get_by_role("button", name=re.compile(label, re.I))
                    if await btn.count():
                        await btn.first.click(timeout=1500)
                        await asyncio.sleep(0.4)
            except Exception:
                logger.debug("scroll @%s load-more click skipped\n%s", username, traceback.format_exc())

            dom_posts = await _extract_posts_from_dom(page)
            added = 0
            for dp in dom_posts:
                if dp.shortcode in seen:
                    continue
                merged.append(dp)
                seen.add(dp.shortcode)
                added += 1

            after_stats = await _dom_stats()
            height_changed = after_stats["height"] != before_stats["height"]
            nodes_changed = after_stats["nodes"] != before_stats["nodes"]
            locator_changed = after_stats["locator"] != before_stats["locator"]
            feed_new = net_feed["count"] - before_feed
            gql_new = net_gql["count"] - before_gql
            network_active = (feed_new + gql_new) > 0
            new_posts = len(merged) - before_posts

            logger.info(
                "scroll @%s n=%s posts=%s (+%s) height=%s (changed=%s) "
                "dom_nodes=%s (changed=%s) locators=%s (changed=%s) "
                "feed_reqs=+%s gql_reqs=+%s network_active=%s target=%s",
                username,
                i + 1,
                len(merged),
                new_posts,
                after_stats["height"],
                height_changed,
                after_stats["nodes"],
                nodes_changed,
                after_stats["locator"],
                locator_changed,
                feed_new,
                gql_new,
                network_active,
                target,
            )

            fully_idle = (
                new_posts == 0
                and not height_changed
                and not network_active
                and not nodes_changed
            )
            if fully_idle:
                idle_streak += 1
                logger.info(
                    "scroll @%s idle_streak=%s/%s (no posts/height/network/dom)",
                    username,
                    idle_streak,
                    idle_needed,
                )
                if idle_streak >= idle_needed:
                    logger.info(
                        "scroll @%s END — idle conditions met collected=%s/%s",
                        username,
                        len(merged),
                        target,
                    )
                    break
            else:
                idle_streak = 0
    finally:
        try:
            page.remove_listener("request", _on_request)
        except Exception:
            pass

    logger.info(
        "scroll @%s finished collected=%s target=%s feed_total=%s gql_total=%s",
        username,
        len(merged),
        target,
        net_feed["count"],
        net_gql["count"],
    )
    return merged


def _merge_media_nodes_into_posts(
    posts: list[ScrapedPost],
    media_nodes: list[dict[str, Any]],
) -> list[ScrapedPost]:
    seen = {p.shortcode for p in posts}
    merged = list(posts)
    for node in media_nodes:
        post = _post_from_node(node)
        if post and post.shortcode not in seen:
            merged.append(post)
            seen.add(post.shortcode)
    return merged


async def _collect_full_timeline_in_browser(
    page,
    *,
    username: str,
    user_id: str,
    expected_count: int,
    existing: list[ScrapedPost],
    media_nodes: list[dict[str, Any]],
    feed_cursors: list[str],
) -> list[ScrapedPost]:
    """Collect the full public timeline via feed API + scroll + network capture.

    Instagram only returns ~12 posts on the profile card. We paginate and scroll
    until we reach posts_count (or exhaust progress).
    """
    posts = _merge_media_nodes_into_posts(existing, media_nodes)
    if expected_count == 0:
        logger.info(
            "browser_timeline @%s expected=0 — empty timeline, skipping collect existing=%s",
            username,
            len(posts),
        )
        return posts

    rounds = 0
    max_rounds = max(25, (expected_count // 6) + 15 if expected_count else 30)
    scroll_delay = float(os.getenv("SCRAPE_SCROLL_DELAY_SECONDS") or "1.0")
    logger.info(
        "browser_timeline @%s start existing=%s expected=%s media_nodes=%s cursors=%s max_rounds=%s",
        username,
        len(posts),
        expected_count,
        len(media_nodes),
        len(feed_cursors),
        max_rounds,
    )

    while rounds < max_rounds and not _posts_complete(posts, expected_count):
        rounds += 1
        before = len(posts)

        posts = _merge_media_nodes_into_posts(posts, media_nodes)

        # Username feed works without user_id; id path is a secondary fallback inside.
        try:
            posts = await _paginate_feed_in_browser(
                page,
                user_id=user_id or "0",
                username=username,
                expected_count=expected_count,
                existing=posts,
            )
        except Exception:
            logger.exception("browser_timeline @%s paginate_feed failed round=%s", username, rounds)

        if _posts_complete(posts, expected_count):
            logger.info("browser_timeline @%s complete after feed paginate posts=%s", username, len(posts))
            break

        if feed_cursors and user_id:
            cursor = feed_cursors[-1]
            try:
                forced = await page.evaluate(
                    """async ({ userId, maxId }) => {
                      const q = new URLSearchParams({ count: '12' });
                      if (maxId) q.set('max_id', String(maxId));
                      const res = await fetch(`/api/v1/feed/user/${userId}/?${q}`, {
                        credentials: 'include',
                        headers: {
                          'X-IG-App-ID': '936619743392459',
                          'X-ASBD-ID': '129477',
                          'X-Requested-With': 'XMLHttpRequest',
                        },
                      });
                      if (!res.ok) return { __error: true, status: res.status, text: await res.text() };
                      return await res.json();
                    }""",
                    {"userId": str(user_id), "maxId": cursor},
                )
                if isinstance(forced, dict) and forced.get("__error"):
                    logger.warning(
                        "browser_timeline @%s forced feed HTTP %s body=%r",
                        username,
                        forced.get("status"),
                        str(forced.get("text") or "")[:180],
                    )
                elif isinstance(forced, dict):
                    for item in forced.get("items") or []:
                        if isinstance(item, dict):
                            media_nodes.append(item)
                    nxt = forced.get("next_max_id")
                    if nxt is not None:
                        text = str(nxt).strip()
                        if text and text not in feed_cursors:
                            feed_cursors.append(text)
            except Exception:
                logger.exception("browser_timeline @%s forced feed cursor failed", username)
            posts = _merge_media_nodes_into_posts(posts, media_nodes)

        if _posts_complete(posts, expected_count):
            break

        try:
            await page.evaluate(
                """(step) => {
                  const h = Math.max(
                    document.body.scrollHeight,
                    document.documentElement.scrollHeight
                  );
                  window.scrollTo(0, Math.min(h, (step + 1) * window.innerHeight * 0.85));
                  if (step % 2 === 1) window.scrollTo(0, h);
                }""",
                rounds,
            )
            await asyncio.sleep(scroll_delay)
            for dp in await _extract_posts_from_dom(page):
                if dp.shortcode not in {p.shortcode for p in posts}:
                    posts.append(dp)
        except Exception:
            logger.exception("browser_timeline @%s scroll/DOM harvest failed round=%s", username, rounds)

        posts = _merge_media_nodes_into_posts(posts, media_nodes)
        logger.info(
            "browser_timeline @%s round=%s posts=%s (+%s) expected=%s",
            username,
            rounds,
            len(posts),
            len(posts) - before,
            expected_count,
        )

        if len(posts) <= before:
            if rounds <= 2:
                try:
                    await page.goto(
                        f"https://www.instagram.com/{username}/reels/",
                        wait_until="domcontentloaded",
                        timeout=45_000,
                    )
                    await asyncio.sleep(scroll_delay)
                    await page.goto(
                        f"https://www.instagram.com/{username}/",
                        wait_until="domcontentloaded",
                        timeout=45_000,
                    )
                    await asyncio.sleep(scroll_delay)
                except Exception:
                    logger.exception("browser_timeline @%s reels/profile reload failed", username)
                continue
            logger.warning(
                "browser_timeline @%s no progress round=%s posts=%s — breaking to full scroll",
                username,
                rounds,
                len(posts),
            )
            break

    if not _posts_complete(posts, expected_count):
        try:
            posts = await _scroll_collect_all_posts(
                page, posts_count=expected_count, existing=posts, username=username
            )
        except Exception:
            logger.exception("browser_timeline @%s full scroll collect failed", username)
        posts = _merge_media_nodes_into_posts(posts, media_nodes)

    logger.info(
        "browser_timeline @%s done posts=%s expected=%s complete=%s",
        username,
        len(posts),
        expected_count,
        _posts_complete(posts, expected_count),
    )
    return posts


async def _paginate_feed_in_browser(
    page,
    *,
    user_id: str,
    username: str,
    expected_count: int,
    existing: list[ScrapedPost],
) -> list[ScrapedPost]:
    """Paginate /api/v1/feed/user/{username}/username/ inside the browser (real IG cookies).

    Username feed path works anonymously; /feed/user/{id}/ often returns 401 require_login.
    This is the reliable path when standalone httpx feed calls only return the
    first profile-card page (~12 posts) or hit rate limits.
    """
    from instascope_scraper.http_profile import (
        _cursor_from_node,
        _max_posts,
        _normalize_cursor,
        _page_size,
        _still_short,
    )

    limit = _max_posts()
    if expected_count > 0:
        limit = min(limit, expected_count)

    merged = list(existing)
    seen = {p.shortcode for p in merged}
    max_id: str | None = None
    # Jump past the first card page using the last known media id
    if merged:
        last_id = merged[-1].ig_post_id
        if last_id:
            text = str(last_id).split("_", 1)[0]
            max_id = text or None
    more = True
    stagnant = 0
    pages = 0
    delay = float(caps_env("SCRAPE_PAGE_DELAY_SECONDS", "0.75") or "0.75")
    page_size = _page_size()
    max_pages = max(80, (limit // max(page_size, 1)) + 40)

    logger.info(
        "browser_feed @%s start have=%s expected=%s seed_max_id=%s max_pages=%s",
        username,
        len(merged),
        expected_count,
        max_id,
        max_pages,
    )

    while more and _still_short(len(merged), limit=limit, expected_count=expected_count) and stagnant < 8 and pages < max_pages:
        pages += 1
        if pages > 1:
            await asyncio.sleep(delay)

        payload = await page.evaluate(
            """async ({ userId, username, maxId, count }) => {
              const q = new URLSearchParams({ count: String(count) });
              if (maxId) q.set('max_id', String(maxId));
              // Username path first — id path returns 401 anonymously
              const paths = [
                `/api/v1/feed/user/${encodeURIComponent(username)}/username/?${q.toString()}`,
                `/api/v1/feed/user/${userId}/?${q.toString()}`,
              ];
              const errors = [];
              for (const url of paths) {
                try {
                  const res = await fetch(url, {
                    credentials: 'include',
                    headers: {
                      'X-IG-App-ID': '936619743392459',
                      'X-ASBD-ID': '129477',
                      'X-Requested-With': 'XMLHttpRequest',
                      'Accept': '*/*',
                    },
                  });
                  const text = await res.text();
                  if (!res.ok) {
                    errors.push({ url: url.slice(0, 100), status: res.status, body: text.slice(0, 160) });
                    continue;
                  }
                  let json;
                  try { json = JSON.parse(text); } catch (e) {
                    errors.push({ url: url.slice(0, 100), status: res.status, body: text.slice(0, 160), parse: String(e) });
                    continue;
                  }
                  if (json && (json.items || json.profile_grid_items || json.status === 'ok')) {
                    return json;
                  }
                  errors.push({ url: url.slice(0, 100), status: res.status, body: text.slice(0, 160) });
                } catch (e) {
                  errors.push({ url: url.slice(0, 100), fetch_error: String(e) });
                }
              }
              return { __error: true, errors, items: [], more_available: false };
            }""",
            {
                "userId": str(user_id),
                "username": username,
                "maxId": max_id,
                "count": page_size,
            },
        )

        if not isinstance(payload, dict) or payload.get("__error"):
            stagnant += 1
            logger.warning(
                "browser_feed @%s page=%s FAILED stagnant=%s max_id=%s errors=%s",
                username,
                pages,
                stagnant,
                max_id,
                json.dumps(payload.get("errors") if isinstance(payload, dict) else payload)[:400],
            )
            continue

        items = payload.get("items") or []
        if not isinstance(items, list):
            items = []
        if not items:
            for entry in payload.get("profile_grid_items") or []:
                if isinstance(entry, dict):
                    media = entry.get("media") if isinstance(entry.get("media"), dict) else entry
                    if isinstance(media, dict):
                        items.append(media)

        next_max = (
            payload.get("next_max_id")
            or payload.get("max_id")
            or payload.get("profile_grid_items_cursor")
        )
        paging = payload.get("paging_info")
        if next_max is None and isinstance(paging, dict):
            next_max = paging.get("max_id")
        cursor = _normalize_cursor(next_max)

        more_flag = payload.get("more_available")
        if more_flag is None:
            more = bool(cursor)
        else:
            more = bool(more_flag)
            if not more and cursor and len(items) >= 1:
                more = True

        added = 0
        last_node: dict[str, Any] | None = None
        for item in items:
            if not isinstance(item, dict):
                continue
            last_node = item
            post = _post_from_node(item)
            if not post or post.shortcode in seen:
                continue
            seen.add(post.shortcode)
            merged.append(post)
            added += 1
            if len(merged) >= limit:
                break

        logger.info(
            "browser_feed @%s page=%s got=%s added=%s total=%s next=%s more=%s more_flag=%s",
            username,
            pages,
            len(items),
            added,
            len(merged),
            cursor,
            more,
            more_flag,
        )

        if added == 0:
            stagnant += 1
            # Advance with response cursor even on duplicates
            if cursor and cursor != max_id:
                max_id = cursor
                continue
        else:
            stagnant = 0

        if cursor and cursor != max_id:
            max_id = cursor
        elif last_node:
            derived = _cursor_from_node(last_node)
            if derived and derived != max_id:
                max_id = derived
                more = more or _still_short(len(merged), limit=limit, expected_count=expected_count)
            else:
                more = False
        else:
            more = False

        if (
            not more
            and _still_short(len(merged), limit=limit, expected_count=expected_count)
            and (cursor or max_id)
        ):
            more = True
            if cursor:
                max_id = cursor

        if expected_count > 0 and len(merged) >= expected_count:
            break

    logger.info(
        "browser_feed @%s done total=%s expected=%s pages=%s stagnant=%s",
        username,
        len(merged),
        expected_count,
        pages,
        stagnant,
    )
    return merged


def _posts_need_view_enrich(posts: list[ScrapedPost], *, weak: int = 1000) -> bool:
    """True when any reel still needs a play-count refresh."""
    del weak  # kept for call-site compat; all reels are refreshed
    for p in posts:
        if p.media_type in {"reel", "video"} or p.is_video:
            # Always refresh reel plays — weak seeds under-count vs public UI.
            return True
    return False


def _is_tunnel_or_proxy_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    needles = (
        "err_tunnel",
        "tunnel_connection",
        "proxy",
        "net::err_",
        "ns_error_proxy",
        "connection refused",
        "timed out",
        "timeout",
        "econnreset",
        "econnrefused",
    )
    return any(n in msg for n in needles)


def _result_is_usable(result: ScrapeResult | None) -> bool:
    if not result:
        return False
    if result.followers > 0 or result.posts_count > 0:
        return True
    if result.posts:
        return True
    # Confirmed empty public/private card still counts as a resolved profile.
    if int(result.posts_count or 0) == 0 and (
        result.ig_user_id or result.avatar_url or result.full_name or result.bio or result.is_private
    ):
        return True
    if result.full_name or result.bio or result.avatar_url:
        return True
    return False


def _has_card_metrics(result: ScrapeResult | None) -> bool:
    """True when follower/following card fields are present (not posts-only feed)."""
    return bool(result and int(result.followers or 0) > 0)


def _merge_card_metrics(base: ScrapeResult, card: ScrapeResult) -> ScrapeResult:
    """Copy identity/card fields from card onto base while keeping base.posts."""
    if card.followers > 0:
        base.followers = card.followers
    if card.following > 0:
        base.following = card.following
    # Lifetime media count from the card must win over a programme-window sample size.
    if card.posts_count > 0 and card.posts_count >= int(base.posts_count or 0):
        base.posts_count = card.posts_count
    if card.full_name and not base.full_name:
        base.full_name = card.full_name
    if card.bio and (not base.bio or base.bio == (base.raw or {}).get("source")):
        # Prefer real bio; meta_desc is a noisy fallback
        if "Followers" not in (card.bio or "") or not base.bio:
            base.bio = card.bio if "Followers" not in (card.bio or "") else base.bio
    if card.avatar_url and not base.avatar_url:
        base.avatar_url = card.avatar_url
    if card.ig_user_id and not base.ig_user_id:
        base.ig_user_id = card.ig_user_id
    if int(getattr(card, "highlight_reel_count", 0) or 0) > 0:
        base.highlight_reel_count = int(card.highlight_reel_count)
    if card.is_verified:
        base.is_verified = True
    if card.is_private:
        base.is_private = True
    return base


async def _fill_card_via_html_meta(
    username: str,
    http_result: ScrapeResult,
    *,
    proxy_url: str | None,
) -> ScrapeResult:
    """Fill followers/following/posts_count from HTML meta without Playwright."""
    # Still fetch meta when lifetime posts_count is missing — followers alone
    # is not enough (programme samples must not stand in for IG lifetime).
    need_posts = int(http_result.posts_count or 0) <= 0
    if _has_card_metrics(http_result) and not need_posts:
        return http_result
    try:
        from instascope_scraper.http_profile import InstagramUserNotFound, fetch_profile_meta_card

        meta = await fetch_profile_meta_card(username, proxy=proxy_url)
        if not meta:
            return http_result
        if meta.get("is_private"):
            http_result.is_private = True
        card = _result_from_meta(
            username,
            meta_desc=meta.get("meta_desc"),
            og_image=meta.get("og_image"),
            og_title=meta.get("og_title"),
        )
        if card and (_has_card_metrics(card) or int(card.posts_count or 0) > 0):
            logger.info(
                "meta_card @%s followers=%s following=%s posts_count=%s",
                username,
                card.followers,
                card.following,
                card.posts_count,
            )
            return _merge_card_metrics(http_result, card)
        if http_result.is_private:
            return http_result
    except InstagramUserNotFound as exc:
        raise ScrapeError(
            f"Profile @{username} does not exist on Instagram",
            unavailable=True,
        ) from exc
    except Exception:
        logger.exception("meta_card fill @%s failed", username)
    return http_result


def _finalize_result(result: ScrapeResult, *, path: str) -> ScrapeResult:
    result.raw = {
        **(result.raw or {}),
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "posts_scraped": len(result.posts),
        "path": path,
    }
    return result


async def _finish_scrape_result(
    username: str,
    result: ScrapeResult,
    *,
    path: str,
    proxy_url: str | None = None,
) -> ScrapeResult:
    """Shared finalize used by HTTP and browser scrape paths."""
    result = await _ensure_lifetime_posts_count(username, result, proxy_url=proxy_url)
    return _finalize_result(result, path=path)


async def _ensure_lifetime_posts_count(
    username: str,
    result: ScrapeResult,
    *,
    proxy_url: str | None,
) -> ScrapeResult:
    """When we stopped at the programme floor, scraped N must not become 'IG lifetime'.

    Fetch HTML meta Posts count when the stored posts_count is missing or equals
    the programme sample size (common bug after username-feed pagination).
    """
    if not _result_hit_cohort_floor(result):
        return result
    scraped_n = len(result.posts or [])
    pc = int(result.posts_count or 0)
    # Already have a lifetime total larger than the programme sample.
    if pc > scraped_n > 0:
        return result
    saved = pc
    # Force meta fill when count is missing or suspiciously equal to the sample.
    if scraped_n > 0 and (pc <= 0 or pc == scraped_n):
        result.posts_count = 0
    try:
        filled = await _fill_card_via_html_meta(username, result, proxy_url=proxy_url)
        meta_pc = int(filled.posts_count or 0)
        if meta_pc > 0 and meta_pc != scraped_n:
            logger.info(
                "lifetime_posts_fix @%s sample=%s was=%s now=%s",
                username,
                scraped_n,
                saved,
                meta_pc,
            )
            return filled
        if meta_pc <= 0 and saved > 0:
            filled.posts_count = saved
        return filled
    except Exception:
        logger.exception("lifetime_posts_fix @%s failed", username)
        result.posts_count = saved
    return result


def _complete(result: ScrapeResult) -> bool:
    """Timeline complete for programme scrape (cohort floor or full/capped count)."""
    return _posts_complete(
        result.posts,
        result.posts_count,
        hit_cohort_floor=_result_hit_cohort_floor(result),
        feed_exhausted=_result_feed_exhausted(result),
    )


async def _scrape_live(
    username: str,
    *,
    headless: bool,
    proxy: Optional[ProxyConfig],
    delay: float,
    on_progress=None,
) -> ScrapeResult:
    # 1) Fast path: public web_profile_info over HTTP — paginate until posts_count
    http_result: ScrapeResult | None = None
    proxy_url = proxy_to_httpx_url(proxy)
    await _emit_progress(on_progress, phase="starting", scraped_posts=0, total_posts=0)

    async def _done(result: ScrapeResult, path: str) -> ScrapeResult:
        nonlocal proxy_url
        return await _finish_scrape_result(
            username, result, path=path, proxy_url=proxy_url
        )

    try:
        from instascope_scraper.http_profile import (
            InstagramUserNotFound,
            fetch_timeline_via_username_feed,
            fetch_web_profile_http,
        )

        await _emit_progress(on_progress, phase="http_profile", scraped_posts=0, total_posts=0)

        # Try each residential port until we get a profile card (avoids one hot IP).
        from instascope_scraper.proxy_pool import all_proxy_httpx_urls, mark_proxy_bad

        candidate_proxies: list[str | None] = []
        if proxy_url:
            candidate_proxies.append(proxy_url)
        for u in all_proxy_httpx_urls():
            if u not in candidate_proxies:
                candidate_proxies.append(u)
        if os.getenv("SCRAPE_DIRECT_FALLBACK", "1") != "0" and None not in candidate_proxies:
            candidate_proxies.append(None)
        if not candidate_proxies:
            candidate_proxies = [None]

        http_json = None
        try:
            for cand in candidate_proxies:
                http_json = await fetch_web_profile_http(username, proxy=cand)
                if http_json:
                    proxy_url = cand
                    break
                if cand:
                    mark_proxy_bad(cand, seconds=60)
        except InstagramUserNotFound as exc:
            raise ScrapeError(
                f"Profile @{username} does not exist on Instagram",
                unavailable=True,
            ) from exc

        user = _user_from_web_profile(http_json) if http_json else None
        if user:
            expected = _expected_posts_count(user)
            # Zero-post public accounts: save the card and move on (no expand/browser).
            # Require an explicit media count — a missing count must NOT look like empty,
            # or we'd finalize 0 posts before pagination finds the real timeline.
            if (
                expected == 0
                and _posts_count_known(user)
                and not bool(user.get("is_private"))
            ):
                http_result = _result_from_user(username, user)
                logger.info(
                    "http_empty @%s followers=%s following=%s — 0 posts, done",
                    username,
                    http_result.followers,
                    http_result.following,
                )
                await _emit_progress(
                    on_progress,
                    phase="done",
                    scraped_posts=0,
                    total_posts=0,
                )
                return await _done(http_result, path="http_empty")

            if not bool(user.get("is_private")):
                try:
                    all_posts, floor_hit = await _expand_all_posts(
                        username, user, proxy_url=proxy_url, on_progress=on_progress
                    )
                    http_result = _result_from_user(username, user, posts_override=all_posts)
                    if floor_hit:
                        _mark_cohort_floor(http_result)
                except Exception:
                    logger.exception("http expand @%s failed — falling back to card edges", username)
                    http_result = _result_from_user(username, user)
            else:
                http_result = _result_from_user(username, user)

            if http_result and http_result.is_private:
                return await _done(http_result, path="http_private")

            # Full programme timeline via HTTP → success immediately (no browser).
            if http_result and _complete(http_result):
                logger.info(
                    "http_full @%s posts=%s/%s cohort_floor=%s",
                    username,
                    len(http_result.posts),
                    http_result.posts_count,
                    _result_hit_cohort_floor(http_result),
                )
                return await _done(http_result, path="http_full")
            if http_result:
                logger.warning(
                    "http_partial @%s posts=%s/%s — escalating to browser",
                    username,
                    len(http_result.posts),
                    http_result.posts_count,
                )
                # Under IG rate limits, browser often hangs forever. Prefer a usable
                # card+sample over zeros unless explicitly forced — BUT never accept a
                # first-page sample as done while SPARK cohort stop is on (must reach
                # 15 Jul 2026 or exhaust the feed).
                force_browser = caps_env("SCRAPE_BROWSER_ON_PARTIAL", "0").strip() == "1"
                cohort_incomplete = False
                try:
                    from instascope_scraper.http_profile import _cohort_floor_unix

                    cohort_incomplete = (
                        _cohort_floor_unix() is not None
                        and not _result_hit_cohort_floor(http_result)
                        and not _result_feed_exhausted(http_result)
                    )
                except Exception:
                    cohort_incomplete = False
                if (
                    not force_browser
                    and not cohort_incomplete
                    and _result_is_usable(http_result)
                    and http_result.followers > 0
                    and len(http_result.posts) > 0
                ):
                    logger.warning(
                        "http_partial @%s returning without browser "
                        "(set SCRAPE_BROWSER_ON_PARTIAL=1 to force)",
                        username,
                    )
                    return await _done(http_result, path="http_partial")
                if cohort_incomplete:
                    logger.warning(
                        "http_partial @%s posts=%s — missing programme floor, continuing",
                        username,
                        len(http_result.posts),
                    )
        else:
            # web_profile_info blocked (401 Please wait) — username feed often still works
            logger.warning("web_profile_info @%s unavailable — trying username feed", username)
            await _emit_progress(on_progress, phase="username_feed", scraped_posts=0, total_posts=0)
            try:
                feed_user, feed_nodes, feed_floor = await fetch_timeline_via_username_feed(
                    username,
                    expected_count=0,
                    proxy=proxy_url,
                    on_progress=on_progress,
                )
                from instascope_scraper.http_profile import (
                    _media_count_known,
                    _parse_media_count,
                )

                # Empty account confirmed via feed user object — finish without browser.
                if (
                    feed_user
                    and _media_count_known(feed_user)
                    and _parse_media_count(feed_user) == 0
                    and not feed_nodes
                ):
                    if "edge_owner_to_timeline_media" not in feed_user:
                        feed_user = {
                            **feed_user,
                            "edge_owner_to_timeline_media": {
                                "count": 0,
                                "edges": [],
                                "page_info": {"has_next_page": False},
                            },
                        }
                    http_result = _result_from_user(username, feed_user, posts_override=[])
                    logger.info(
                        "username_feed_empty @%s followers=%s — 0 posts, done",
                        username,
                        http_result.followers,
                    )
                    await _emit_progress(
                        on_progress, phase="done", scraped_posts=0, total_posts=0
                    )
                    return await _done(http_result, path="username_feed_empty")

                if feed_nodes:
                    posts = _posts_from_nodes(feed_nodes)
                    if feed_user:
                        # Normalize feed user shape for _result_from_user.
                        # Do NOT fall back to len(posts) — that is the programme sample,
                        # not Instagram lifetime media_count.
                        if "edge_owner_to_timeline_media" not in feed_user:
                            from instascope_scraper.http_profile import _parse_media_count

                            known = _parse_media_count(feed_user)
                            feed_user = {
                                **feed_user,
                                "edge_owner_to_timeline_media": {
                                    "count": known,
                                    "edges": [],
                                    "page_info": {"has_next_page": False},
                                },
                            }
                        http_result = _result_from_user(username, feed_user, posts_override=posts)
                    else:
                        # Never invent lifetime posts_count from the programme sample.
                        # 0 = unknown until meta / web_profile fills the real IG total.
                        http_result = ScrapeResult(
                            username=username,
                            ig_user_id=None,
                            full_name=None,
                            bio=None,
                            website=None,
                            avatar_url=None,
                            is_verified=False,
                            followers=0,
                            following=0,
                            posts_count=0,
                            posts=posts,
                            raw={"source": "username_feed"},
                        )
                    if feed_floor:
                        _mark_cohort_floor(http_result)
                    if http_result and (
                        _complete(http_result)
                        or (http_result.posts_count < 0 and len(http_result.posts) > 12)
                    ):
                        # If posts_count unknown (<0 sentinel unused), trust feed exhaustion
                        # ONLY when we did not stop at the programme floor (sample ≠ lifetime).
                        if (
                            http_result.posts_count < 0
                            and not _result_hit_cohort_floor(http_result)
                        ):
                            http_result.posts_count = len(http_result.posts)
                        if (
                            http_result.posts_count <= 0
                            and len(http_result.posts) > 12
                            and not _result_hit_cohort_floor(http_result)
                        ):
                            http_result.posts_count = len(http_result.posts)
                        if _complete(http_result):
                            # Feed user payload is thin (often no follower_count) — only
                            # short-circuit when card metrics exist; else fill card via
                            # HTML meta (no Playwright) so bulk/single keep posts + counts.
                            if _has_card_metrics(http_result):
                                logger.info(
                                    "username_feed_full @%s posts=%s/%s followers=%s cohort_floor=%s",
                                    username,
                                    len(http_result.posts),
                                    http_result.posts_count,
                                    http_result.followers,
                                    feed_floor,
                                )
                                return await _done(http_result, path="username_feed_full")
                            http_result = await _fill_card_via_html_meta(
                                username, http_result, proxy_url=proxy_url
                            )
                            if feed_floor:
                                _mark_cohort_floor(http_result)
                            if _has_card_metrics(http_result):
                                return await _done(
                                    http_result, path="username_feed_meta"
                                )
                            # Keep posts; fall through to browser only if enabled.
                            # Do NOT finalize with followers=0 — that drops card fields.
                            logger.info(
                                "username_feed_posts @%s posts=%s/%s followers=0 — "
                                "need card fill (browser if enabled)",
                                username,
                                len(http_result.posts),
                                http_result.posts_count,
                            )
                    if http_result and _result_is_usable(http_result) and _has_card_metrics(
                        http_result
                    ):
                        if _complete(http_result):
                            logger.warning(
                                "username_feed_partial @%s posts=%s/%s — keeping usable HTTP",
                                username,
                                len(http_result.posts),
                                http_result.posts_count,
                            )
                            return await _done(http_result, path="username_feed_partial")
                        logger.warning(
                            "username_feed_partial @%s posts=%s/%s — incomplete programme window",
                            username,
                            len(http_result.posts),
                            http_result.posts_count,
                        )
                    if http_result and _result_is_usable(http_result):
                        http_result = await _fill_card_via_html_meta(
                            username, http_result, proxy_url=proxy_url
                        )
                        if _has_card_metrics(http_result) and _complete(http_result):
                            return await _done(
                                http_result, path="username_feed_partial_meta"
                            )
                    logger.warning(
                        "username_feed_partial @%s posts=%s/%s — escalating to browser",
                        username,
                        len(http_result.posts) if http_result else 0,
                        http_result.posts_count if http_result else 0,
                    )
            except InstagramUserNotFound as exc:
                raise ScrapeError(
                    f"Profile @{username} does not exist on Instagram",
                    unavailable=True,
                ) from exc
            except Exception:
                logger.exception("username_feed @%s failed", username)
    except ScrapeError:
        # Not-found / definitive failures must not fall through to browser.
        raise
    except Exception:
        logger.exception("http fast-path @%s crashed", username)
        http_result = None

    # Prefer HTTP with card metrics over Playwright. Posts-only (followers=0) is
    # not "done" — try HTML meta first, then browser if enabled.
    if http_result and _result_is_usable(http_result) and not _has_card_metrics(http_result):
        proxy_url = proxy_to_httpx_url(proxy) if proxy is not None else None
        http_result = await _fill_card_via_html_meta(
            username, http_result, proxy_url=proxy_url
        )
    if http_result and http_result.is_private:
        return await _done(http_result, path="http_private")
    if http_result and _result_is_usable(http_result) and _has_card_metrics(http_result):
        if _complete(http_result):
            return await _done(http_result, path="http_full")
        logger.warning(
            "http_usable @%s posts=%s/%s followers=%s — programme window incomplete, continuing",
            username,
            len(http_result.posts),
            http_result.posts_count,
            http_result.followers,
        )

    # API card blocked (common for private) — detect private from HTML before failing.
    proxy_url = proxy_to_httpx_url(proxy) if proxy is not None else None
    try:
        from instascope_scraper.http_profile import InstagramUserNotFound as _IgNotFound

        private_card = await _try_private_from_html(username, proxy_url=proxy_url)
        if private_card:
            return private_card
    except Exception as exc:
        from instascope_scraper.http_profile import InstagramUserNotFound as _IgNotFound

        if isinstance(exc, _IgNotFound):
            raise ScrapeError(
                f"Profile @{username} does not exist on Instagram",
                unavailable=True,
            ) from exc
        logger.exception("private html fallback @%s failed", username)

    use_browser = caps_env("SCRAPE_USE_BROWSER", "1").strip() not in {"0", "false", "no"}
    if not use_browser:
        # Keep posts-only HTTP rather than failing the whole queue job.
        if http_result and _result_is_usable(http_result):
            logger.warning(
                "http_posts_only @%s posts=%s followers=0 — browser disabled",
                username,
                len(http_result.posts),
            )
            return await _done(http_result, path="http_posts_only")
        raise ScrapeError(
            "Instagram rate-limited this server IP (no profile card/posts via HTTP). "
            "Wait a few minutes and Refresh, or set SCRAPE_PROXY_URL to a residential proxy. "
            "Set SCRAPE_INLINE_USE_BROWSER=1 only if Playwright+proxy is configured."
        )

    # 2) Browser path only when HTTP returned nothing usable
    try:
        await _emit_progress(
            on_progress,
            phase="browser",
            scraped_posts=len(http_result.posts) if http_result else 0,
            total_posts=(http_result.posts_count if http_result else 0) or 0,
        )
        result = await _scrape_live_browser(
            username,
            headless=headless,
            proxy=proxy,
            delay=delay,
            http_result=http_result,
            on_progress=on_progress,
        )
        # If browser still short, force one more HTTP expand toward posts_count
        if (
            result
            and not result.is_private
            and not _complete(result)
            and result.ig_user_id
        ):
            try:
                from instascope_scraper.http_profile import fetch_web_profile_http

                proxy_url = proxy_to_httpx_url(proxy)
                http_json = await fetch_web_profile_http(username, proxy=proxy_url)
                user = _user_from_web_profile(http_json) if http_json else None
                if user:
                    more, floor_hit = await _expand_all_posts(username, user, proxy_url=proxy_url)
                    result.posts = _merge_posts(result.posts, more)
                    if floor_hit:
                        _mark_cohort_floor(result)
                    if _complete(result):
                        return await _done(result, path="http_after_browser")
            except Exception:
                logger.exception("http_after_browser @%s failed", username)
            # Username feed rescue when web_profile still blocked
            if not _complete(result):
                try:
                    from instascope_scraper.http_profile import fetch_timeline_via_username_feed

                    _, feed_nodes, feed_floor = await fetch_timeline_via_username_feed(
                        username,
                        expected_count=result.posts_count,
                        proxy=proxy_to_httpx_url(proxy),
                    )
                    result.posts = _merge_posts(result.posts, _posts_from_nodes(feed_nodes))
                    if feed_floor:
                        _mark_cohort_floor(result)
                    if _complete(result):
                        return await _done(result, path="username_feed_after_browser")
                except Exception:
                    logger.exception("username_feed_after_browser @%s failed", username)
        try:
            _raise_if_incomplete(result)
        except ScrapeError:
            if _result_is_usable(result):
                logger.warning(
                    "incomplete browser @%s posts=%s/%s — saving usable partial",
                    username,
                    len(result.posts),
                    result.posts_count,
                )
                return await _done(result, path="browser_partial")
            if http_result and _result_is_usable(http_result):
                return await _done(http_result, path="http_partial_kept")
            raise
        return await _done(result, path="browser")
    except Exception as exc:
        # Prefer a complete HTTP timeline; otherwise keep any usable card/posts
        # rather than failing with zeros after a browser/proxy hang.
        if http_result and _complete(http_result):
            return await _done(http_result, path="http_fallback_complete")
        if http_result and _result_is_usable(http_result):
            logger.warning(
                "browser failed @%s (%s) — saving usable HTTP result posts=%s followers=%s",
                username,
                exc,
                len(http_result.posts),
                http_result.followers,
            )
            return await _done(http_result, path="http_partial_after_browser_fail")

        # Always attempt HTTP rescue after browser/extract failures (not only proxy tunnels).
        # Datacenter IPs often fail browser login-wall while HTTP still returns a card.
        try:
            from instascope_scraper.http_profile import (
                fetch_timeline_via_username_feed,
                fetch_web_profile_http,
            )

            proxy_candidates: list[str | None] = []
            if proxy is not None:
                proxy_candidates.append(proxy_to_httpx_url(proxy))
            proxy_candidates.append(None)  # direct
            for use_proxy in proxy_candidates:
                try:
                    await _emit_progress(
                        on_progress,
                        phase="http_rescue",
                        scraped_posts=0,
                        total_posts=0,
                    )
                    http_json = await fetch_web_profile_http(username, proxy=use_proxy)
                    user = _user_from_web_profile(http_json) if http_json else None
                    if user:
                        posts, floor_hit = await _expand_all_posts(
                            username, user, proxy_url=use_proxy, on_progress=on_progress
                        )
                        rescued = _result_from_user(username, user, posts_override=posts)
                        if floor_hit:
                            _mark_cohort_floor(rescued)
                        if _result_is_usable(rescued):
                            if _complete(rescued):
                                return await _done(rescued, path="http_rescue_full")
                            return await _done(rescued, path="http_rescue_partial")
                    feed_user, feed_nodes, feed_floor = await fetch_timeline_via_username_feed(
                        username,
                        expected_count=0,
                        proxy=use_proxy,
                        on_progress=on_progress,
                    )
                    if feed_nodes:
                        posts = _posts_from_nodes(feed_nodes)
                        if feed_user:
                            rescued = _result_from_user(
                                username, feed_user, posts_override=posts
                            )
                        else:
                            rescued = ScrapeResult(
                                username=username,
                                ig_user_id=None,
                                full_name=None,
                                bio=None,
                                website=None,
                                avatar_url=None,
                                is_verified=False,
                                followers=0,
                                following=0,
                                posts_count=0,
                                posts=posts,
                                raw={"source": "username_feed_rescue"},
                            )
                        if feed_floor:
                            _mark_cohort_floor(rescued)
                        # Do not invent lifetime count from the programme sample.
                        if (
                            rescued.posts_count <= 0
                            and not _result_hit_cohort_floor(rescued)
                            and len(posts) > 0
                        ):
                            rescued.posts_count = len(posts)
                        if _result_is_usable(rescued):
                            return await _done(rescued, path="username_feed_rescue")
                except Exception:
                    logger.exception(
                        "http rescue @%s proxy=%s failed", username, bool(use_proxy)
                    )
                    continue
        except Exception:
            logger.exception("http rescue outer @%s failed", username)

        if _is_tunnel_or_proxy_error(exc) and proxy is not None:
            try:
                from instascope_scraper.http_profile import (
                    fetch_timeline_via_username_feed,
                    fetch_web_profile_http,
                )

                for use_proxy in (proxy_to_httpx_url(proxy), None):
                    try:
                        http_json = await fetch_web_profile_http(username, proxy=use_proxy)
                        user = _user_from_web_profile(http_json) if http_json else None
                        if user:
                            posts, floor_hit = await _expand_all_posts(username, user, proxy_url=use_proxy)
                            result = _result_from_user(username, user, posts_override=posts)
                            if floor_hit:
                                _mark_cohort_floor(result)
                            if _complete(result):
                                return await _done(result, path="http_after_tunnel_fail")
                        feed_user, feed_nodes, feed_floor = await fetch_timeline_via_username_feed(
                            username, expected_count=0, proxy=use_proxy
                        )
                        if feed_nodes and feed_user:
                            posts = _posts_from_nodes(feed_nodes)
                            result = _result_from_user(username, feed_user, posts_override=posts)
                            if feed_floor:
                                _mark_cohort_floor(result)
                            if (
                                result.posts_count <= 0
                                and not _result_hit_cohort_floor(result)
                                and len(posts) > 0
                            ):
                                result.posts_count = len(posts)
                            if _complete(result):
                                return await _done(result, path="username_feed_after_tunnel")
                    except Exception:
                        logger.exception("tunnel fallback @%s proxy=%s failed", username, bool(use_proxy))
                        continue
            except Exception:
                logger.exception("tunnel fallback outer @%s failed", username)
        if isinstance(exc, ScrapeError):
            msg = str(exc)
            if "proxy" not in msg.lower() and "blocked" not in msg.lower():
                raise ScrapeError(
                    f"{msg} Set SCRAPE_PROXY_URL to a residential proxy if this server "
                    f"IP is blocked by Instagram."
                ) from exc
            raise
        raise ScrapeError(str(exc)) from exc


async def _scrape_live_browser(
    username: str,
    *,
    headless: bool,
    proxy: Optional[ProxyConfig],
    delay: float,
    http_result: ScrapeResult | None,
    on_progress=None,
) -> ScrapeResult:
    from instascope_scraper.http_profile import _timeline_from_user

    proxy_url = proxy_to_httpx_url(proxy)

    async def _done(result: ScrapeResult, path: str) -> ScrapeResult:
        return await _finish_scrape_result(
            username, result, path=path, proxy_url=proxy_url
        )

    url = f"https://www.instagram.com/{username}/"
    captured: list[dict[str, Any]] = []
    media_nodes: list[dict[str, Any]] = []
    feed_cursors: list[str] = []

    await _emit_progress(
        on_progress,
        phase="browser_launch",
        scraped_posts=len(http_result.posts) if http_result else 0,
        total_posts=(http_result.posts_count if http_result else 0) or 0,
    )
    async with browser_session(headless=headless, proxy=proxy) as browser:
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1365, "height": 900},
            locale="en-US",
        )
        await context.set_extra_http_headers(
            {
                "Accept-Language": "en-US,en;q=0.9",
                "X-IG-App-ID": "936619743392459",
            }
        )
        page = await context.new_page()

        async def on_response(response):
            try:
                u = response.url
                if response.status != 200:
                    return
                if "web_profile_info" in u or "/api/v1/users/web_profile_info" in u:
                    captured.append(await response.json())
                    return
                if "graphql/query" in u or "/api/v1/feed/user/" in u:
                    try:
                        payload = await response.json()
                    except Exception:
                        return
                    if not isinstance(payload, dict):
                        return
                    user = (payload.get("data") or {}).get("user")
                    if isinstance(user, dict):
                        nodes, cursor, _ = _timeline_from_user(user)
                        media_nodes.extend(nodes)
                        if cursor:
                            text = str(cursor).strip()
                            if text and text not in feed_cursors:
                                feed_cursors.append(text)
                    items = payload.get("items")
                    if isinstance(items, list):
                        media_nodes.extend([it for it in items if isinstance(it, dict)])
                    nxt = payload.get("next_max_id")
                    if nxt is not None:
                        text = str(nxt).strip()
                        if text and text not in feed_cursors:
                            feed_cursors.append(text)
            except Exception:
                pass

        page.on("response", on_response)

        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        except Exception as exc:
            await context.close()
            if http_result and _complete(http_result):
                http_result.raw = {
                    **(http_result.raw or {}),
                    "browser_error": str(exc)[:400],
                }
                return await _done(http_result, path="http_fallback_goto")
            raise ScrapeError(str(exc)) from exc

        await asyncio.sleep(max(delay, 2.0))

        try:
            body_text = (await page.locator("body").inner_text(timeout=5_000))[:2000].lower()
        except Exception:
            body_text = ""
        # Soft-404 copy only. Bare HTTP 404 from IG is often a login/API shell for
        # accounts that still exist (e.g. bare handles like samaaa.says).
        if (
            "sorry, this page isn't available" in body_text
            or "the link you followed may be broken" in body_text
            or "page isn't available" in body_text
        ):
            await context.close()
            raise ScrapeError(
                f"Profile @{username} does not exist on Instagram",
                unavailable=True,
            )
        if (
            "this account is private" in body_text
            or "account is private" in body_text
            or "follow to see their photos and videos" in body_text
        ):
            # Prefer any HTTP card we already have; otherwise save a private stub.
            if http_result:
                http_result.is_private = True
                await context.close()
                return await _done(http_result, path="browser_private")
            await context.close()
            return await _done(
                ScrapeResult(
                    username=username,
                    ig_user_id=None,
                    full_name=None,
                    bio=None,
                    website=None,
                    avatar_url=None,
                    is_verified=False,
                    followers=0,
                    following=0,
                    posts_count=0,
                    posts=[],
                    is_private=True,
                    raw={"source": "browser_private"},
                ),
                path="browser_private",
            )

        for label in ("Allow all cookies", "Allow essential and optional cookies", "Accept"):
            try:
                btn = page.get_by_role("button", name=re.compile(label, re.I))
                if await btn.count():
                    await btn.first.click(timeout=2000)
                    await asyncio.sleep(0.5)
                    break
            except Exception:
                pass

        user_payload = None
        for raw in captured:
            user_payload = _user_from_web_profile(raw) or user_payload
        if not user_payload:
            api_json = await _fetch_web_profile_info(page, username)
            if api_json:
                user_payload = _user_from_web_profile(api_json)

        result: ScrapeResult | None = http_result
        if user_payload:
            seeded = list(result.posts) if result and result.posts else None
            result = _result_from_user(username, user_payload, posts_override=seeded)
        elif not result:
            meta_desc = await page.locator('meta[name="description"]').get_attribute("content")
            og_image = await page.locator('meta[property="og:image"]').get_attribute("content")
            og_title = await page.locator('meta[property="og:title"]').get_attribute("content")
            result = _result_from_meta(
                username, meta_desc=meta_desc, og_image=og_image, og_title=og_title
            )

        # HTTP username-feed often returns posts without follower_count — fill from meta
        if result and result.followers <= 0:
            try:
                meta_desc = await page.locator('meta[name="description"]').get_attribute(
                    "content", timeout=5_000
                )
                og_image = await page.locator('meta[property="og:image"]').get_attribute(
                    "content", timeout=3_000
                )
                og_title = await page.locator('meta[property="og:title"]').get_attribute(
                    "content", timeout=3_000
                )
                meta = _result_from_meta(
                    username, meta_desc=meta_desc, og_image=og_image, og_title=og_title
                )
                if meta:
                    if meta.followers > 0:
                        result.followers = meta.followers
                    if meta.following > 0:
                        result.following = meta.following
                    if meta.posts_count > 0 and result.posts_count <= 0:
                        result.posts_count = meta.posts_count
                    if not result.avatar_url and meta.avatar_url:
                        result.avatar_url = meta.avatar_url
                    if not result.full_name and meta.full_name:
                        result.full_name = meta.full_name
                    logger.info(
                        "browser @%s filled card from meta followers=%s following=%s posts_count=%s",
                        username,
                        result.followers,
                        result.following,
                        result.posts_count,
                    )
            except Exception:
                logger.warning(
                    "browser @%s meta card fill skipped (login wall or missing tags)\n%s",
                    username,
                    traceback.format_exc(),
                )

        if not result:
            title = await page.title()
            await context.close()
            if http_result and _result_is_usable(http_result):
                logger.warning(
                    "browser @%s empty page (title=%r) — keeping HTTP result posts=%s followers=%s",
                    username,
                    title,
                    len(http_result.posts),
                    http_result.followers,
                )
                return await _done(http_result, path="http_kept_after_empty_browser")
            if "login" in (title or "").lower():
                raise ScrapeError(
                    "Instagram login wall blocked scraping. Set SCRAPE_PROXY_URL to a "
                    "residential proxy (datacenter/VPS IPs are usually blocked)."
                )
            raise ScrapeError(
                "Could not extract real profile data from Instagram "
                "(IP likely blocked). Set SCRAPE_PROXY_URL to a residential proxy."
            )

        og_image = await page.locator('meta[property="og:image"]').get_attribute("content")
        og_title = await page.locator('meta[property="og:title"]').get_attribute("content")
        if not result.avatar_url and og_image:
            result.avatar_url = og_image
        if not result.full_name and og_title:
            result.full_name = og_title.split("(")[0].strip() or result.full_name

        user_id = result.ig_user_id or (
            str(user_payload.get("id") or user_payload.get("pk") or "") if user_payload else ""
        )

        # Full timeline for public profiles — skip when HTTP already completed it
        if not result.is_private and not _complete(result):
            try:
                result.posts = await _collect_full_timeline_in_browser(
                    page,
                    username=username,
                    user_id=user_id or "",
                    expected_count=result.posts_count,
                    existing=result.posts,
                    media_nodes=media_nodes,
                    feed_cursors=feed_cursors,
                )
            except Exception:
                logger.exception("browser_timeline collect @%s failed", username)
                result.posts = _merge_media_nodes_into_posts(result.posts, media_nodes)
        elif not result.is_private:
            logger.info(
                "browser @%s skipping timeline — already complete posts=%s/%s",
                username,
                len(result.posts),
                result.posts_count,
            )

        # Last-chance HTTP expand with cookies already warmed by browser session
        if not result.is_private and not _complete(result):
            try:
                proxy_url = proxy_to_httpx_url(proxy)
                if user_payload:
                    more_posts, floor_hit = await _expand_all_posts(username, user_payload, proxy_url=proxy_url)
                    seen = {p.shortcode for p in result.posts}
                    for p in more_posts:
                        if p.shortcode not in seen:
                            result.posts.append(p)
                            seen.add(p.shortcode)
                    if floor_hit:
                        _mark_cohort_floor(result)
                if not _complete(result):
                    from instascope_scraper.http_profile import fetch_timeline_via_username_feed

                    _, feed_nodes, feed_floor = await fetch_timeline_via_username_feed(
                        username,
                        expected_count=result.posts_count,
                        proxy=proxy_url,
                    )
                    result.posts = _merge_posts(result.posts, _posts_from_nodes(feed_nodes))
                    if feed_floor:
                        _mark_cohort_floor(result)
            except Exception:
                logger.exception("browser last-chance HTTP expand @%s failed", username)

        if not result.posts:
            dom_posts = await _extract_posts_from_dom(page)
            if dom_posts:
                result.posts = dom_posts

        if result.posts and not result.is_private:
            missing = [
                p
                for p in result.posts
                if (p.likes == 0 and p.comments == 0)
                or (p.media_type in {"reel", "video"} or p.is_video)
            ]
            missing.sort(
                key=lambda p: 0 if (p.media_type in {"reel", "video"} or p.is_video) else 1
            )
            enrich_cap_env = int(caps_env("SCRAPE_ENRICH_MAX", "0") or "0")
            if enrich_cap_env <= 0:
                enrich_cap = len(missing)
            else:
                enrich_cap = min(enrich_cap_env, len(missing))
            if missing and enrich_cap > 0:
                to_enrich = missing[:enrich_cap]
                enrich_codes = {p.shortcode for p in to_enrich}
                prioritized = to_enrich + [p for p in result.posts if p.shortcode not in enrich_codes]
                try:
                    enriched = await _enrich_posts(page, prioritized, limit=enrich_cap)
                    by_code = {p.shortcode: p for p in enriched}
                    result.posts = [by_code.get(p.shortcode, p) for p in result.posts]
                except Exception:
                    logger.exception("browser enrich @%s failed", username)

        await context.close()

        if not _result_is_usable(result):
            raise ScrapeError("Scraped profile returned empty metrics")

        # Must reach Instagram posts_count — never accept first-card-only (~12).
        if not result.is_private and not _complete(result):
            if http_result and len(http_result.posts) > len(result.posts):
                result.posts = list(http_result.posts)
            if not _complete(result):
                _raise_if_incomplete(result)

        return await _done(result, path="browser_full")


async def scrape_profile(
    username: str,
    *,
    headless: bool = True,
    proxy: Optional[ProxyConfig] = None,
    delay_seconds: float = 2.0,
    live: Optional[bool] = None,
    on_progress=None,
    caps: ScrapeCaps | None = None,
) -> ScrapeResult:
    """Always scrapes live Instagram data. `live` is kept for API compatibility."""
    if caps is not None:
        with use_caps(caps):
            return await _scrape_profile_inner(
                username,
                headless=headless,
                proxy=proxy,
                delay_seconds=delay_seconds,
                live=live,
                on_progress=on_progress,
            )
    return await _scrape_profile_inner(
        username,
        headless=headless,
        proxy=proxy,
        delay_seconds=delay_seconds,
        live=live,
        on_progress=on_progress,
    )


async def _scrape_profile_inner(
    username: str,
    *,
    headless: bool = True,
    proxy: Optional[ProxyConfig] = None,
    delay_seconds: float = 2.0,
    live: Optional[bool] = None,
    on_progress=None,
) -> ScrapeResult:
    """Always scrapes live Instagram data. `live` is kept for API compatibility."""
    _ = live  # ignored — real data only
    if os.getenv("LIVE_SCRAPE", "1") == "0":
        raise ScrapeError("LIVE_SCRAPE=0 — enable LIVE_SCRAPE=1 for real scraping")

    from instascope_scraper.proxy_pool import mark_proxy_bad, next_proxy, pool_size, proxy_label
    from instascope_scraper.types import parse_proxy_url

    if proxy is not None and proxy.server and "@" in proxy.server:
        parsed = parse_proxy_url(proxy.server)
        if parsed:
            proxy = parsed

    # Prefer rotating residential pool; fall back to a single SCRAPE_PROXY_URL.
    rotate = pool_size() > 0
    if proxy is None:
        proxy = next_proxy() if rotate else parse_proxy_url(os.getenv("SCRAPE_PROXY_URL") or None)

    last_err: Exception | None = None
    attempts = int(caps_env("SCRAPE_MAX_RETRIES", "3") or "3")
    # When we have multiple ports, try up to pool size (capped) so rate-limits rotate away.
    if rotate:
        attempts = max(attempts, min(pool_size(), 5))
    logger.info(
        "scrape_profile @%s start attempts=%s headless=%s proxy=%s pool=%s",
        username,
        attempts,
        headless,
        proxy_label(proxy),
        pool_size(),
    )
    for attempt in range(max(attempts, 1)):
        if attempt > 0 and rotate:
            proxy = next_proxy(exclude=proxy)
        try:
            await _emit_progress(
                on_progress,
                phase="starting",
                scraped_posts=0,
                total_posts=0,
            )
            result = await _scrape_live(
                username,
                headless=headless,
                proxy=proxy,
                delay=delay_seconds + min(attempt, 2),
                on_progress=on_progress,
            )
            logger.info(
                "scrape_profile @%s OK attempt=%s posts=%s/%s path=%s proxy=%s",
                username,
                attempt + 1,
                len(result.posts),
                result.posts_count,
                (result.raw or {}).get("path"),
                proxy_label(proxy),
            )
            await _emit_progress(
                on_progress,
                phase="done",
                scraped_posts=len(result.posts),
                total_posts=result.posts_count or len(result.posts),
            )
            return result
        except ScrapeError as exc:
            # Don't burn retries on definitive not-found
            if exc.unavailable:
                raise
            last_err = exc
            msg = str(exc).lower()
            if any(
                n in msg
                for n in (
                    "rate-limited",
                    "rate limited",
                    "please wait",
                    "login wall",
                    "could not extract",
                    "tunnel",
                    "proxy",
                    "timed out",
                    "timeout",
                )
            ):
                mark_proxy_bad(proxy)
            logger.warning(
                "scrape_profile @%s ScrapeError attempt=%s/%s proxy=%s: %s",
                username,
                attempt + 1,
                attempts,
                proxy_label(proxy),
                exc,
            )
            await asyncio.sleep(delay_seconds * (attempt + 1))
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            mark_proxy_bad(proxy)
            logger.warning(
                "scrape_profile @%s error attempt=%s/%s proxy=%s: %s",
                username,
                attempt + 1,
                attempts,
                proxy_label(proxy),
                exc,
            )
            await asyncio.sleep(delay_seconds * (attempt + 1))

    raise ScrapeError(_humanize_scrape_error(last_err or "Scrape failed after retries"))


def _humanize_scrape_error(err: BaseException | str) -> str:
    raw = str(err)
    low = raw.lower()
    if "err_tunnel" in low or "tunnel_connection" in low:
        return (
            "Proxy tunnel failed while opening Instagram. "
            "Check Decodo proxy; HTTP fallback may still work on Refresh."
        )
    if "login wall" in low or ("login" in low and "blocked" in low):
        return (
            "Instagram showed a login wall. "
            "Residential proxy may need verification or a fresh session."
        )
    if "not found" in low:
        return raw
    if len(raw) > 220:
        return raw[:217] + "..."
    return raw
