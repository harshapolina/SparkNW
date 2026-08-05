"""Real Instagram profile + posts scraping via Playwright.

No demo/fake data. Fails loudly if Instagram blocks or the profile is unavailable.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Optional

from instascope_scraper.browser import browser_session
from instascope_scraper.types import ProxyConfig, ScrapedPost, ScrapeResult, proxy_to_httpx_url


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


def _post_from_node(node: dict[str, Any]) -> ScrapedPost | None:
    shortcode = node.get("shortcode") or node.get("code")
    post_id = str(node.get("id") or node.get("pk") or shortcode or "")
    if not shortcode and not post_id:
        return None
    shortcode = shortcode or post_id
    taken = node.get("taken_at_timestamp") or node.get("taken_at")
    posted_at = None
    if taken:
        try:
            posted_at = datetime.fromtimestamp(int(taken), tz=timezone.utc).isoformat()
        except (TypeError, ValueError, OSError):
            posted_at = None

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
    views = _parse_count(
        node.get("video_view_count")
        or node.get("video_play_count")
        or node.get("play_count")
        or node.get("view_count")
        or node.get("ig_play_count")
        or 0
    )
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
            child_views += _parse_count(
                child.get("video_view_count")
                or child.get("video_play_count")
                or child.get("play_count")
                or child.get("view_count")
                or 0
            )
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


def _posts_complete(posts: list[ScrapedPost], posts_count: int) -> bool:
    """True when we've collected essentially the full public timeline."""
    if not posts:
        return False
    if posts_count <= 0:
        # Unknown total — never treat the first profile-card page (~12) as complete.
        return len(posts) > 12
    # Allow tiny mismatch (deleted/hidden posts between count and feed).
    return len(posts) >= max(posts_count - 2, 1) or len(posts) >= posts_count


async def _expand_all_posts(username: str, user: dict[str, Any], *, proxy_url: str | None) -> list[ScrapedPost]:
    """Paginate Instagram timeline until all (or max) posts are collected."""
    from instascope_scraper.http_profile import _timeline_from_user, fetch_all_media_nodes

    user_id = str(user.get("id") or user.get("pk") or "")
    if not user_id:
        # Fall back to first-page only
        result = _result_from_user(username, user)
        return result.posts

    expected = _expected_posts_count(user)
    initial_nodes, cursor, has_next = _timeline_from_user(user)
    # Also seed from alternate media shapes already parsed via _result_from_user
    seed = _result_from_user(username, user).posts
    seed_nodes = initial_nodes
    all_nodes = await fetch_all_media_nodes(
        username,
        user_id=user_id,
        initial_nodes=seed_nodes,
        initial_cursor=cursor,
        initial_has_next=has_next,
        expected_count=expected,
        proxy=proxy_url,
    )

    posts: list[ScrapedPost] = []
    seen: set[str] = set()
    for node in all_nodes:
        post = _post_from_node(node)
        if not post:
            continue
        if post.shortcode in seen:
            continue
        seen.add(post.shortcode)
        posts.append(post)

    # Keep any seed posts GraphQL might have missed field-wise
    for p in seed:
        if p.shortcode not in seen:
            seen.add(p.shortcode)
            posts.append(p)

    return posts


def _enrich_limit(total_posts: int) -> int:
    """How many posts to open for missing likes/comments/views. 0 = all."""
    raw = (os.getenv("SCRAPE_ENRICH_MAX") or "0").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 0
    if n <= 0:
        return total_posts
    return min(n, total_posts)



def _result_from_meta(username: str, *, meta_desc: str | None, og_image: str | None, og_title: str | None) -> ScrapeResult | None:
    if not meta_desc:
        return None
    followers = following = posts_count = 0
    m = re.search(r"([\d.,]+[KMB]?)\s+Followers", meta_desc, flags=re.I)
    if m:
        followers = _parse_count(m.group(1))
    m = re.search(r"([\d.,]+[KMB]?)\s+Following", meta_desc, flags=re.I)
    if m:
        following = _parse_count(m.group(1))
    m = re.search(r"([\d.,]+[KMB]?)\s+Posts", meta_desc, flags=re.I)
    if m:
        posts_count = _parse_count(m.group(1))
    if followers == 0 and posts_count == 0:
        return None
    full_name = None
    if og_title:
        full_name = og_title.split("(")[0].strip() or None
        # Strip trailing "• Instagram photos and videos"
        if full_name and "instagram" in full_name.lower():
            full_name = re.split(r"\s*[•|]\s*", full_name)[0].strip()
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
                posted_at=None,
            )
        )
    return posts


async def _enrich_posts(page, posts: list[ScrapedPost], *, limit: int | None = None) -> list[ScrapedPost]:
    """Open individual post pages to fill likes/comments/views when missing.

    By default enriches every post that is missing engagement details
    (SCRAPE_ENRICH_MAX=0). Set SCRAPE_ENRICH_MAX to cap for very large profiles.
    """
    if limit is None:
        limit = _enrich_limit(len(posts))
    delay = float(os.getenv("SCRAPE_ENRICH_DELAY_SECONDS") or "0.9")
    enriched: list[ScrapedPost] = []
    visited = 0
    for post in posts:
        if visited >= limit:
            enriched.append(post)
            continue
        # Still open reels/videos if views are missing (likes alone are not enough)
        needs_views = (post.media_type in {"reel", "video"} or post.is_video) and post.views < 10
        if (post.likes or post.comments) and not needs_views:
            enriched.append(post)
            continue
        if post.views >= 10 and (post.likes or post.comments):
            enriched.append(post)
            continue
        visited += 1
        try:
            resp = await page.goto(post.permalink, wait_until="domcontentloaded", timeout=30_000)
            await asyncio.sleep(delay)
            if resp and resp.status == 404:
                enriched.append(post)
                continue
            meta = await page.locator('meta[name="description"]').get_attribute("content")
            likes = comments = views = 0
            if meta:
                # Examples vary: "1,234 Likes, 56 Comments - caption"
                lm = re.search(r"([\d.,]+[KMB]?)\s+Likes?", meta, flags=re.I)
                cm = re.search(r"([\d.,]+[KMB]?)\s+Comments?", meta, flags=re.I)
                vm = re.search(r"([\d.,]+[KMB]?)\s+views?", meta, flags=re.I)
                if lm:
                    likes = _parse_count(lm.group(1))
                if cm:
                    comments = _parse_count(cm.group(1))
                if vm:
                    views = _parse_count(vm.group(1))
            og_image = await page.locator('meta[property="og:image"]').get_attribute("content")
            enriched.append(
                ScrapedPost(
                    ig_post_id=post.ig_post_id,
                    shortcode=post.shortcode,
                    media_type=post.media_type,
                    caption=post.caption or (meta.split("-", 1)[-1].strip() if meta and "-" in meta else post.caption),
                    thumbnail_url=og_image or post.thumbnail_url,
                    permalink=post.permalink,
                    likes=likes or post.likes,
                    comments=comments or post.comments,
                    views=views or post.views,
                    posted_at=post.posted_at,
                    is_video=post.is_video,
                    accessibility_caption=post.accessibility_caption,
                )
            )
        except Exception:
            enriched.append(post)
    return enriched


async def _scroll_collect_all_posts(page, *, posts_count: int, existing: list[ScrapedPost]) -> list[ScrapedPost]:
    """Infinite-scroll the profile grid until all public posts are visible in the DOM."""
    from instascope_scraper.http_profile import _max_posts

    hard_cap = _max_posts()
    target = min(posts_count if posts_count > 0 else hard_cap, hard_cap)
    merged = list(existing)
    seen = {p.shortcode for p in merged}
    stagnant = 0
    # ~12 posts per scroll batch; allow plenty of room for slow lazy-loads
    max_scrolls = max(80, (target // 2) + 40)
    scroll_delay = float(os.getenv("SCRAPE_SCROLL_DELAY_SECONDS") or "1.1")

    for i in range(max_scrolls):
        if target > 0 and len(merged) >= target:
            break
        # Progressive scroll — IG lazy-loads better than a single jump to bottom
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
            pass
        dom_posts = await _extract_posts_from_dom(page)
        added = 0
        for dp in dom_posts:
            if dp.shortcode in seen:
                continue
            merged.append(dp)
            seen.add(dp.shortcode)
            added += 1
        if added == 0:
            stagnant += 1
            if stagnant >= 8:
                break
        else:
            stagnant = 0

    return merged


async def _paginate_feed_in_browser(
    page,
    *,
    user_id: str,
    expected_count: int,
    existing: list[ScrapedPost],
) -> list[ScrapedPost]:
    """Paginate /api/v1/feed/user/{id}/ inside the browser (uses real IG cookies).

    This is the reliable path when standalone httpx feed calls only return the
    first profile-card page (~12 posts).
    """
    from instascope_scraper.http_profile import _max_posts

    limit = _max_posts()
    if expected_count > 0:
        limit = min(limit, expected_count)

    merged = list(existing)
    seen = {p.shortcode for p in merged}
    max_id: str | None = None
    more = True
    stagnant = 0
    pages = 0
    delay = float(os.getenv("SCRAPE_PAGE_DELAY_SECONDS") or "0.75")
    page_size = 12
    max_pages = max(40, (limit // page_size) + 20)

    while more and len(merged) < limit and stagnant < 5 and pages < max_pages:
        pages += 1
        if pages > 1:
            await asyncio.sleep(delay)

        payload = await page.evaluate(
            """async ({ userId, maxId, count }) => {
              const q = new URLSearchParams({ count: String(count) });
              if (maxId) q.set('max_id', String(maxId));
              const paths = [
                `/api/v1/feed/user/${userId}/?${q.toString()}`,
                `https://www.instagram.com/api/v1/feed/user/${userId}/?${q.toString()}`,
              ];
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
                  if (!res.ok) continue;
                  const json = await res.json();
                  if (json && (json.items || json.status === 'ok')) return json;
                } catch (e) {}
              }
              return { __error: true, items: [], more_available: false };
            }""",
            {"userId": str(user_id), "maxId": max_id, "count": page_size},
        )

        if not isinstance(payload, dict) or payload.get("__error"):
            stagnant += 1
            continue

        items = payload.get("items") or []
        more = bool(payload.get("more_available"))
        next_max = payload.get("next_max_id")
        max_id = str(next_max) if next_max is not None else None

        added = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            post = _post_from_node(item)
            if not post or post.shortcode in seen:
                continue
            seen.add(post.shortcode)
            merged.append(post)
            added += 1
            if len(merged) >= limit:
                break

        if added == 0:
            stagnant += 1
        else:
            stagnant = 0

        if not max_id:
            break
        if expected_count > 0 and len(merged) >= expected_count:
            break

    return merged


async def _scrape_live(
    username: str,
    *,
    headless: bool,
    proxy: Optional[ProxyConfig],
    delay: float,
) -> ScrapeResult:
    # 1) Fast path: public web_profile_info over HTTP (metrics + first ~12 posts)
    http_result: ScrapeResult | None = None
    try:
        from instascope_scraper.http_profile import fetch_web_profile_http

        proxy_url = proxy_to_httpx_url(proxy)
        http_json = await fetch_web_profile_http(username, proxy=proxy_url)
        user = _user_from_web_profile(http_json) if http_json else None
        if user:
            # Try HTTP pagination, but NEVER trust it as final if still ~12 of many
            if not bool(user.get("is_private")):
                try:
                    all_posts = await _expand_all_posts(username, user, proxy_url=proxy_url)
                    http_result = _result_from_user(username, user, posts_override=all_posts)
                except Exception:
                    http_result = _result_from_user(username, user)
            else:
                http_result = _result_from_user(username, user)

            # Only skip browser when timeline is truly complete (or private / tiny account)
            if http_result and http_result.is_private:
                http_result.raw = {
                    **(http_result.raw or {}),
                    "scraped_at": datetime.now(timezone.utc).isoformat(),
                    "posts_scraped": len(http_result.posts),
                    "path": "http_private",
                }
                return http_result
            if http_result and _posts_complete(http_result.posts, http_result.posts_count):
                needs_enrich = (
                    http_result.posts
                    and all(p.likes == 0 and p.comments == 0 for p in http_result.posts[: min(6, len(http_result.posts))])
                )
                if not needs_enrich and len(http_result.posts) > 12:
                    http_result.raw = {
                        **(http_result.raw or {}),
                        "scraped_at": datetime.now(timezone.utc).isoformat(),
                        "posts_scraped": len(http_result.posts),
                        "path": "http_full",
                    }
                    return http_result
                if not needs_enrich and http_result.posts_count <= 12:
                    http_result.raw = {
                        **(http_result.raw or {}),
                        "scraped_at": datetime.now(timezone.utc).isoformat(),
                        "posts_scraped": len(http_result.posts),
                        "path": "http_full_small",
                    }
                    return http_result
            # Incomplete → Playwright browser feed pagination (required)
    except Exception:
        http_result = None

    from instascope_scraper.http_profile import _timeline_from_user

    url = f"https://www.instagram.com/{username}/"
    captured: list[dict[str, Any]] = []
    media_nodes: list[dict[str, Any]] = []

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
                    user = (payload.get("data") or {}).get("user") if isinstance(payload, dict) else None
                    if isinstance(user, dict):
                        nodes, _, _ = _timeline_from_user(user)
                        media_nodes.extend(nodes)
                    items = payload.get("items") if isinstance(payload, dict) else None
                    if isinstance(items, list):
                        media_nodes.extend([it for it in items if isinstance(it, dict)])
            except Exception:
                pass

        page.on("response", on_response)

        response = await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        await asyncio.sleep(max(delay, 2.0))

        if response and response.status == 404:
            await context.close()
            raise ScrapeError(f"Profile @{username} not found", unavailable=True)

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

        if not result:
            title = await page.title()
            await context.close()
            if "login" in (title or "").lower():
                raise ScrapeError(
                    "Instagram login wall blocked scraping. Add SCRAPE_PROXY_URL or session cookies."
                )
            raise ScrapeError("Could not extract real profile data from Instagram")

        og_image = await page.locator('meta[property="og:image"]').get_attribute("content")
        og_title = await page.locator('meta[property="og:title"]').get_attribute("content")
        if not result.avatar_url and og_image:
            result.avatar_url = og_image
        if not result.full_name and og_title:
            result.full_name = og_title.split("(")[0].strip() or result.full_name

        user_id = result.ig_user_id or (str(user_payload.get("id") or user_payload.get("pk") or "") if user_payload else "")

        # PRIMARY: paginate feed API inside the browser (real cookies + proxy)
        if not result.is_private and user_id and not _posts_complete(result.posts, result.posts_count):
            try:
                result.posts = await _paginate_feed_in_browser(
                    page,
                    user_id=user_id,
                    expected_count=result.posts_count,
                    existing=result.posts,
                )
            except Exception:
                pass

        # Merge network-captured nodes
        if media_nodes and not result.is_private:
            seen = {p.shortcode for p in result.posts}
            for node in media_nodes:
                post = _post_from_node(node)
                if post and post.shortcode not in seen:
                    result.posts.append(post)
                    seen.add(post.shortcode)

        # SECONDARY: DOM scroll for any remaining shortcodes
        if not result.is_private and not _posts_complete(result.posts, result.posts_count):
            try:
                result.posts = await _scroll_collect_all_posts(
                    page, posts_count=result.posts_count, existing=result.posts
                )
            except Exception:
                pass

        # THIRD: HTTP expand again using cookies from the browser session (export cookies)
        if not result.is_private and not _posts_complete(result.posts, result.posts_count) and user_payload:
            try:
                proxy_url = proxy_to_httpx_url(proxy)
                more_posts = await _expand_all_posts(username, user_payload, proxy_url=proxy_url)
                seen = {p.shortcode for p in result.posts}
                for p in more_posts:
                    if p.shortcode not in seen:
                        result.posts.append(p)
                        seen.add(p.shortcode)
            except Exception:
                pass

        if not result.posts:
            dom_posts = await _extract_posts_from_dom(page)
            if dom_posts:
                result.posts = dom_posts

        # Enrich only posts still missing engagement (feed items usually have counts)
        if result.posts and not result.is_private:
            missing = [
                p
                for p in result.posts
                if (p.likes == 0 and p.comments == 0)
                or ((p.media_type in {"reel", "video"} or p.is_video) and p.views < 10)
            ]
            enrich_cap_env = int(os.getenv("SCRAPE_ENRICH_MAX") or "0")
            if enrich_cap_env <= 0:
                enrich_cap = min(len(missing), 40)
            else:
                enrich_cap = min(enrich_cap_env, len(missing))
            if missing and enrich_cap > 0:
                to_enrich = missing[:enrich_cap]
                enrich_codes = {p.shortcode for p in to_enrich}
                prioritized = to_enrich + [p for p in result.posts if p.shortcode not in enrich_codes]
                enriched = await _enrich_posts(page, prioritized, limit=enrich_cap)
                by_code = {p.shortcode: p for p in enriched}
                result.posts = [by_code.get(p.shortcode, p) for p in result.posts]

        await context.close()

        if result.followers <= 0 and result.posts_count <= 0 and not result.posts:
            raise ScrapeError("Scraped profile returned empty metrics")

        # Do NOT accept profile-card-only scrapes as success for large accounts
        if (
            not result.is_private
            and result.posts_count > 12
            and len(result.posts) <= 12
        ):
            raise ScrapeError(
                f"Incomplete timeline: only {len(result.posts)}/{result.posts_count} posts "
                f"(Instagram pagination blocked). Check SCRAPE_PROXY_URL / Decodo."
            )

        result.raw = {
            **(result.raw or {}),
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "posts_scraped": len(result.posts),
            "path": "browser_full",
        }
        return result


async def scrape_profile(
    username: str,
    *,
    headless: bool = True,
    proxy: Optional[ProxyConfig] = None,
    delay_seconds: float = 2.0,
    live: Optional[bool] = None,
) -> ScrapeResult:
    """Always scrapes live Instagram data. `live` is kept for API compatibility."""
    _ = live  # ignored — real data only
    if os.getenv("LIVE_SCRAPE", "1") == "0":
        # Explicit opt-out only
        raise ScrapeError("LIVE_SCRAPE=0 — enable LIVE_SCRAPE=1 for real scraping")

    if proxy is None:
        from instascope_scraper.types import parse_proxy_url

        proxy = parse_proxy_url(os.getenv("SCRAPE_PROXY_URL") or None)
    elif proxy.server and "@" in proxy.server:
        # Caller passed a full http://user:pass@host:port as server only
        from instascope_scraper.types import parse_proxy_url

        parsed = parse_proxy_url(proxy.server)
        if parsed:
            proxy = parsed

    last_err: Exception | None = None
    attempts = int(os.getenv("SCRAPE_MAX_RETRIES", "3"))
    for attempt in range(max(attempts, 1)):
        try:
            return await _scrape_live(
                username,
                headless=headless,
                proxy=proxy,
                delay=delay_seconds + attempt,
            )
        except ScrapeError:
            raise
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            await asyncio.sleep(delay_seconds * (attempt + 1))
    raise ScrapeError(str(last_err or "Scrape failed after retries"))
