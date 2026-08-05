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

    # HTTP media-info pass for reel play counts (before browser enrich)
    try:
        posts = await _enrich_views_via_http(posts, username=username, proxy_url=proxy_url)
    except Exception:
        pass

    return posts


async def _enrich_views_via_http(
    posts: list[ScrapedPost],
    *,
    username: str,
    proxy_url: str | None,
) -> list[ScrapedPost]:
    """Fill reel play counts via /api/v1/media/{id}/info/ over HTTP+proxy."""
    import httpx
    from instascope_scraper.http_profile import _apply_csrf, _bootstrap_session, _client_headers

    weak = int(os.getenv("SCRAPE_WEAK_VIEWS_THRESHOLD") or "1000")
    delay = float(os.getenv("SCRAPE_ENRICH_DELAY_SECONDS") or "0.5")
    targets = [
        p
        for p in posts
        if (p.media_type in {"reel", "video"} or p.is_video) and p.views < weak and p.ig_post_id
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
    """Open individual post/reel pages to fill likes/comments/views.

    Reels always get a view/play-count pass when views look missing or weak,
    because feed payloads often under-report play_count vs the public UI.
    """
    if limit is None:
        limit = _enrich_limit(len(posts))
    delay = float(os.getenv("SCRAPE_ENRICH_DELAY_SECONDS") or "0.9")
    # Reels with "some" views can still be under-counted; re-check below this bar
    weak_views = int(os.getenv("SCRAPE_WEAK_VIEWS_THRESHOLD") or "1000")
    enriched: list[ScrapedPost] = []
    visited = 0

    for post in posts:
        is_reelish = post.media_type in {"reel", "video"} or post.is_video
        needs_views = is_reelish and post.views < weak_views
        needs_eng = post.likes == 0 and post.comments == 0
        if visited >= limit:
            enriched.append(post)
            continue
        if not needs_views and not needs_eng:
            enriched.append(post)
            continue
        if post.views >= weak_views and (post.likes or post.comments) and not needs_views:
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


def _posts_need_view_enrich(posts: list[ScrapedPost], *, weak: int = 1000) -> bool:
    """True when any reel/video is missing a believable play count."""
    for p in posts:
        if p.media_type in {"reel", "video"} or p.is_video:
            if p.views < weak:
                return True
    return False


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

            # Only skip browser when timeline is complete AND reel views look real
            if http_result and http_result.is_private:
                http_result.raw = {
                    **(http_result.raw or {}),
                    "scraped_at": datetime.now(timezone.utc).isoformat(),
                    "posts_scraped": len(http_result.posts),
                    "path": "http_private",
                }
                return http_result

            weak = int(os.getenv("SCRAPE_WEAK_VIEWS_THRESHOLD") or "1000")
            if (
                http_result
                and _posts_complete(http_result.posts, http_result.posts_count)
                and not _posts_need_view_enrich(http_result.posts, weak=weak)
            ):
                needs_likes = (
                    http_result.posts
                    and all(
                        p.likes == 0 and p.comments == 0
                        for p in http_result.posts[: min(6, len(http_result.posts))]
                    )
                )
                if not needs_likes:
                    http_result.raw = {
                        **(http_result.raw or {}),
                        "scraped_at": datetime.now(timezone.utc).isoformat(),
                        "posts_scraped": len(http_result.posts),
                        "path": "http_full",
                    }
                    return http_result
            # Missing posts and/or reel views → Playwright enrich path
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

        # Enrich reels for accurate play counts (feed often under-reports vs IG UI)
        if result.posts and not result.is_private:
            weak = int(os.getenv("SCRAPE_WEAK_VIEWS_THRESHOLD") or "1000")
            missing = [
                p
                for p in result.posts
                if (p.likes == 0 and p.comments == 0)
                or ((p.media_type in {"reel", "video"} or p.is_video) and p.views < weak)
            ]
            # Prefer reels first so max/avg views match Instagram
            missing.sort(
                key=lambda p: 0 if (p.media_type in {"reel", "video"} or p.is_video) else 1
            )
            enrich_cap_env = int(os.getenv("SCRAPE_ENRICH_MAX") or "0")
            if enrich_cap_env <= 0:
                # Small accounts: enrich everything; larger: up to 80
                enrich_cap = len(missing) if len(result.posts) <= 40 else min(len(missing), 80)
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
