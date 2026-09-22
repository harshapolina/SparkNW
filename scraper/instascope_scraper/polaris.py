"""Logged-out Polaris timeline reader.

Instagram closed anonymous access to the old endpoints in Sep 2026:

- ``/api/v1/users/web_profile_info/``      -> HTTP 429, empty body (every IP)
- ``/api/v1/feed/user/<name>/username/``   -> HTTP 401 ``require_login: true``
- ``/graphql/query?query_hash=...``        -> HTTP 401 "Please wait a few minutes"
- profile HTML fetched over plain httpx    -> data-free app shell
- profile page in a browser                -> renders 12 posts, then a login-wall
  modal that pins ``scrollHeight`` to the viewport, so infinite scroll never fires

What *does* still work, logged out and for free: the server-rendered profile HTML
delivered to a real browser embeds a Relay preload payload, and the query it names
(``PolarisLoggedOutDesktopWWWProfilePostsTabContentQuery``) can be re-POSTed to
``/api/graphql`` with the page's own ``lsd`` token to walk the whole timeline.

The payload uses a different schema from the legacy scraper — the connection is
``polaris_ordered_timeline_connection`` and the shortcode field is ``code``, not
``shortcode`` — which is why the old parsers find nothing in it.

Engagement counts are absent from that payload; they come from the public
``/p/<code>/embed/captioned/`` document, which carries them HTML-escaped.

Every request here is issued from inside the Playwright page context so it
inherits the browser's cookies, client hints and TLS fingerprint. The same calls
made from httpx get the data-free shell. This path works with
``network_policy`` blocking enabled, because it reads the server-rendered payload
and drives pagination itself instead of relying on Instagram's JS bundles.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

from instascope_scraper.types import ScrapedPost

logger = logging.getLogger("instascope.scraper.polaris")

FRIENDLY_NAME = "PolarisLoggedOutDesktopWWWProfilePostsTabContentQuery"
IG_APP_ID = "936619743392459"

# Instagram media ids are Snowflake-like: the high bits hold a ms timestamp.
_PK_EPOCH_MS = 1314220021721
_PK_SHIFT = 23

_RE_DOC_ID = re.compile(
    r'PostsTabContentQueryRelayPreloader_[^"]*","queryID":"(\d+)"'
)
_RE_LSD = re.compile(r'"LSD",\[\],\{"token":"([^"]+)"')
_RE_TIMELINE_CURSOR = re.compile(
    r'"page_info":\{"end_cursor":"([^"]+)","has_next_page":true\}\},"id":"\d+"\}\}'
)
_RE_INLINE_NODE = re.compile(r'"pk":"(\d+)","code":"([A-Za-z0-9_-]{5,20})"')
_RE_FOLLOWERS = re.compile(r'"follower_count":(\d+)')
_RE_FOLLOWING = re.compile(r'"following_count":(\d+)')
_RE_FULL_NAME = re.compile(r'"full_name":"((?:[^"\\]|\\.)*)"')
_RE_IS_PRIVATE = re.compile(r'"is_private":(true|false)')
_RE_USER_ID = re.compile(r'"xig_user_by_username":\{"pk":"(\d+)"')

# Engagement lives in the embed document, sometimes escaped and sometimes not,
# so every field is matched in both forms. Likes are `edge_liked_by`.
def _count_patterns(*names: str) -> tuple[re.Pattern[str], ...]:
    out: list[re.Pattern[str]] = []
    for name in names:
        out.append(re.compile(r'\\"%s\\":\{\\"count\\":(\d+)' % name))
        out.append(re.compile(r'"%s":\{"count":(\d+)' % name))
    return tuple(out)


def _scalar_patterns(*names: str) -> tuple[re.Pattern[str], ...]:
    out: list[re.Pattern[str]] = []
    for name in names:
        out.append(re.compile(r'\\"%s\\":(\d+)' % name))
        out.append(re.compile(r'"%s":(\d+)' % name))
    return tuple(out)


_ENGAGEMENT_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "likes": _count_patterns("edge_liked_by", "edge_media_preview_like")
    + _scalar_patterns("like_count"),
    "comments": _count_patterns("edge_media_to_comment", "edge_media_preview_comment")
    + _scalar_patterns("comment_count"),
    "views": _scalar_patterns("video_view_count", "play_count", "video_play_count"),
}

# Re-POST the preloaded Relay query with our own cursor.
_PAGE_JS = """
async ([docId, lsd, username, after, pageSize]) => {
  const body = new URLSearchParams({
    av: "0", __d: "www", __user: "0", __a: "1", __req: "b", dpr: "1",
    lsd: lsd, jazoest: "2996",
    fb_api_caller_class: "RelayModern",
    fb_api_req_friendly_name: "%FRIENDLY%",
    server_timestamps: "true",
    doc_id: docId,
    variables: JSON.stringify({
      username: username, after: after, before: null, first: pageSize, last: null
    }),
  });
  const r = await fetch("/api/graphql", {
    method: "POST",
    headers: {
      "content-type": "application/x-www-form-urlencoded",
      "x-fb-lsd": lsd,
      "x-ig-app-id": "%APPID%",
      "x-fb-friendly-name": "%FRIENDLY%",
      "x-requested-with": "XMLHttpRequest",
    },
    body: body.toString(),
    credentials: "include",
  });
  return { status: r.status, text: await r.text() };
}
""".replace("%FRIENDLY%", FRIENDLY_NAME).replace("%APPID%", IG_APP_ID)

_EMBED_JS = """
async (code) => {
  try {
    const r = await fetch(`/p/${code}/embed/captioned/`, { credentials: "include" });
    return { status: r.status, text: await r.text() };
  } catch (e) {
    return { status: 0, text: "" };
  }
}
"""


class PolarisUnavailable(RuntimeError):
    """The page did not carry a Polaris preload payload (blocked / not found)."""


def pk_to_datetime(pk: Any) -> datetime | None:
    """Instagram media pk -> UTC creation time (the id embeds a ms timestamp)."""
    try:
        value = int(str(pk))
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    ms = (value >> _PK_SHIFT) + _PK_EPOCH_MS
    try:
        dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    # Guard against ids that are not media pks.
    if not (2010 <= dt.year <= datetime.now(timezone.utc).year + 1):
        return None
    return dt


def _page_size() -> int:
    raw = (os.getenv("SCRAPE_POLARIS_PAGE_SIZE") or "12").strip()
    try:
        return max(1, min(50, int(raw)))
    except ValueError:
        return 12


def _max_pages(expected: int) -> int:
    raw = (os.getenv("SCRAPE_POLARIS_MAX_PAGES") or "").strip()
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    size = _page_size()
    if expected > 0:
        return max(5, (expected // size) + 8)
    return 200


def _unescape_json_str(raw: str) -> str:
    try:
        return json.loads(f'"{raw}"')
    except Exception:
        return raw.replace('\\"', '"').replace("\\/", "/").replace("\\\\", "\\")


def _json_object_at(text: str, start: int) -> Any:
    """Parse the JSON object/array that begins at ``start`` by brace matching."""
    opener = text[start]
    closer = {"{": "}", "[": "]"}.get(opener)
    if closer is None:
        return None
    depth = 0
    in_str = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except Exception:
                    return None
    return None


def _first_page(html: str) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Full node objects and page_info for the server-rendered first page.

    Falls back to a pk/code regex when the payload shape changes, so a schema
    tweak degrades to thinner posts instead of losing the page entirely. The
    page_info is then None, meaning "unknown" rather than "no more posts".
    """
    key = '"polaris_ordered_timeline_connection":'
    idx = html.find(key)
    if idx >= 0:
        brace = html.find("{", idx + len(key))
        if brace >= 0:
            conn = _json_object_at(html, brace)
            if isinstance(conn, dict):
                nodes = [
                    e.get("node") or {}
                    for e in (conn.get("edges") or [])
                    if isinstance(e, dict)
                ]
                nodes = [n for n in nodes if n.get("code")]
                info = conn.get("page_info")
                if nodes:
                    return nodes, info if isinstance(info, dict) else None
    return (
        [{"pk": pk, "code": code} for pk, code in dict.fromkeys(_RE_INLINE_NODE.findall(html))],
        None,
    )


def extract_bootstrap(html: str) -> dict[str, Any]:
    """Pull the Relay doc_id, lsd token, profile card and first page out of the HTML.

    Raises PolarisUnavailable when the page has no Polaris payload.
    """
    doc = _RE_DOC_ID.search(html)
    lsd = _RE_LSD.search(html)
    if not doc or not lsd:
        raise PolarisUnavailable(
            f"no Polaris preload payload (doc_id={bool(doc)} lsd={bool(lsd)})"
        )

    nodes, page_info = _first_page(html)
    if page_info is not None:
        has_next = page_info.get("has_next_page")
        cursor = page_info.get("end_cursor") if has_next else None
    else:
        # Payload shape unknown: a cursor means more pages, but its absence
        # proves nothing, so the end of the timeline stays unconfirmed.
        cursor_match = _RE_TIMELINE_CURSOR.search(html)
        cursor = cursor_match.group(1) if cursor_match else None
        has_next = True if cursor else None

    followers = _RE_FOLLOWERS.search(html)
    following = _RE_FOLLOWING.search(html)
    full_name = _RE_FULL_NAME.search(html)
    private = _RE_IS_PRIVATE.search(html)
    user_id = _RE_USER_ID.search(html)

    return {
        "doc_id": doc.group(1),
        "lsd": lsd.group(1),
        "cursor": cursor,
        # True / False from Instagram's own page_info; None when unknown.
        "has_next": has_next,
        "nodes": nodes,
        "followers": int(followers.group(1)) if followers else None,
        "following": int(following.group(1)) if following else None,
        "full_name": _unescape_json_str(full_name.group(1)) if full_name else None,
        "is_private": private.group(1) == "true" if private else None,
        "ig_user_id": user_id.group(1) if user_id else None,
    }


def _nodes_from_payload(
    payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], str | None, bool | None]:
    """Return (nodes, next_cursor, has_next) from one /api/graphql timeline response.

    ``has_next`` is Instagram's own page_info flag, or None when absent.
    """
    user = ((payload or {}).get("data") or {}).get("xig_user_by_username") or {}
    conn = user.get("polaris_ordered_timeline_connection") or {}
    edges = conn.get("edges") or []
    nodes = [e.get("node") or {} for e in edges if isinstance(e, dict)]
    nodes = [n for n in nodes if n.get("code")]
    info = conn.get("page_info")
    has_next = info.get("has_next_page") if isinstance(info, dict) else None
    nxt = info.get("end_cursor") if has_next else None
    return nodes, nxt, has_next if isinstance(has_next, bool) else None


async def collect_timeline(
    page,
    username: str,
    *,
    html: str | None = None,
    cohort_floor_unix: int | None = None,
    expected_count: int = 0,
    max_posts: int = 0,
    delay_seconds: float = 0.7,
) -> dict[str, Any]:
    """Walk the whole logged-out timeline. Returns bootstrap fields + nodes.

    Stops early once posts fall before ``cohort_floor_unix`` (newest-first order),
    which keeps programme scrapes from paging through years of old content, or
    once ``max_posts`` is reached — bulk sheets take a capped first pass and let
    the deep follow-up fetch the rest. ``max_posts`` of 0 means no cap.
    """
    if html is None:
        html = await page.content()
    boot = extract_bootstrap(html)

    seen: dict[str, dict[str, Any]] = {}
    for node in boot["nodes"]:
        seen[node["code"]] = node

    cursor = boot["cursor"]
    pages = 0
    limit = _max_pages(expected_count)
    size = _page_size()
    hit_floor = False
    # Only Instagram's explicit has_next_page=false proves we saw every post.
    # A stalled or failed page is never treated as the end of the timeline.
    complete = boot.get("has_next") is False

    while cursor and pages < limit:
        try:
            res = await page.evaluate(
                _PAGE_JS, [boot["doc_id"], boot["lsd"], username, cursor, size]
            )
        except Exception:
            logger.exception("polaris @%s page=%s evaluate failed", username, pages + 1)
            break

        status = int(res.get("status") or 0)
        text = res.get("text") or ""
        if status != 200 or not text:
            logger.warning(
                "polaris @%s page=%s HTTP %s body=%r",
                username,
                pages + 1,
                status,
                text[:180],
            )
            break

        try:
            payload = json.loads(text)
        except Exception:
            logger.warning("polaris @%s page=%s non-JSON body=%r", username, pages + 1, text[:180])
            break

        nodes, cursor, has_next = _nodes_from_payload(payload)
        if has_next is False:
            complete = True
        if not nodes:
            break

        new = 0
        for node in nodes:
            code = node.get("code")
            if code and code not in seen:
                seen[code] = node
                new += 1

        pages += 1

        if max_posts > 0 and len(seen) >= max_posts:
            logger.info(
                "polaris @%s hit max_posts=%s after page=%s", username, max_posts, pages
            )
            break

        if cohort_floor_unix is not None:
            oldest = min(
                (
                    dt.timestamp()
                    for dt in (pk_to_datetime(n.get("pk")) for n in nodes)
                    if dt is not None
                ),
                default=None,
            )
            if oldest is not None and oldest < cohort_floor_unix:
                hit_floor = True
                logger.info(
                    "polaris @%s reached cohort floor after page=%s posts=%s",
                    username,
                    pages,
                    len(seen),
                )
                break

        if new == 0:
            logger.info("polaris @%s page=%s returned no new posts — stopping", username, pages)
            break

        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)

    logger.info(
        "polaris @%s collected=%s expected=%s pages=%s floor=%s complete=%s",
        username,
        len(seen),
        expected_count,
        pages,
        hit_floor,
        complete,
    )

    nodes = list(seen.values())
    truncated = max_posts > 0 and len(nodes) > max_posts
    if truncated:
        nodes.sort(
            key=lambda n: (pk_to_datetime(n.get("pk")) or datetime.min.replace(tzinfo=timezone.utc)),
            reverse=True,
        )
        nodes = nodes[:max_posts]
    boot["nodes"] = nodes
    boot["pages"] = pages
    boot["hit_cohort_floor"] = hit_floor
    # Every post Instagram has for this account is in ``nodes``: it said there
    # were no more pages and nothing was dropped by the max_posts cap. For an
    # account whose whole history is inside the programme window this is the
    # only proof of completeness — it never reaches the cohort floor.
    boot["timeline_complete"] = complete and not truncated
    boot["feed_exhausted"] = boot["timeline_complete"]
    boot["capped"] = bool(max_posts > 0 and len(seen) >= max_posts)
    return boot


def _media_type(node: dict[str, Any]) -> tuple[str, bool]:
    typename = str(node.get("__typename") or "")
    product = str(node.get("product_type") or "")
    raw_type = str(node.get("media_type") or "")
    is_video = "Video" in typename or product in {"clips", "igtv"} or raw_type == "2"
    if product == "clips":
        return "reel", True
    if raw_type == "8":
        return "carousel", is_video
    return ("video" if is_video else "image"), is_video


def _caption_text(node: dict[str, Any]) -> str | None:
    cap = node.get("caption")
    if isinstance(cap, dict):
        text = cap.get("text")
        return str(text) if text else None
    if isinstance(cap, str):
        return cap or None
    return None


def nodes_to_posts(
    nodes: list[dict[str, Any]],
    *,
    username: str,
    cohort_floor_unix: int | None = None,
) -> list[ScrapedPost]:
    """Map Polaris timeline nodes onto ScrapedPost, deriving dates from the pk."""
    posts: list[ScrapedPost] = []
    seen: set[str] = set()
    for node in nodes:
        code = str(node.get("code") or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)

        dt = pk_to_datetime(node.get("pk"))
        if cohort_floor_unix is not None and dt is not None:
            if dt.timestamp() < cohort_floor_unix:
                continue

        media_type, is_video = _media_type(node)
        posts.append(
            ScrapedPost(
                ig_post_id=str(node.get("pk") or code),
                shortcode=code,
                media_type=media_type,
                caption=_caption_text(node),
                thumbnail_url=node.get("display_uri") or None,
                permalink=f"https://www.instagram.com/p/{code}/",
                likes=0,
                comments=0,
                views=0,
                posted_at=dt.isoformat() if dt else None,
                is_video=is_video,
                accessibility_caption=node.get("accessibility_caption") or None,
            )
        )
    posts.sort(key=lambda p: p.posted_at or "", reverse=True)
    return posts


def parse_engagement(embed_html: str) -> dict[str, int]:
    """Pull likes / comments / views out of an embed document."""
    out: dict[str, int] = {}
    for key, patterns in _ENGAGEMENT_PATTERNS.items():
        for pattern in patterns:
            m = pattern.search(embed_html)
            if not m:
                continue
            try:
                out[key] = int(m.group(1))
            except ValueError:
                continue
            break
    return out


async def enrich_engagement(
    page,
    posts: list[ScrapedPost],
    *,
    username: str,
    limit: int = 0,
    delay_seconds: float = 0.4,
) -> int:
    """Fill likes/comments/views from /p/<code>/embed/captioned/.

    ``limit`` of 0 means every post. Enrichment is best-effort: a post that fails
    keeps its zeroed counters rather than failing the scrape.
    """
    targets = posts if limit <= 0 else posts[:limit]
    filled = 0
    for post in targets:
        try:
            res = await page.evaluate(_EMBED_JS, post.shortcode)
        except Exception:
            logger.debug("polaris enrich @%s %s evaluate failed", username, post.shortcode)
            continue
        if int(res.get("status") or 0) != 200:
            continue
        data = parse_engagement(res.get("text") or "")
        if not data:
            continue
        post.likes = max(int(post.likes or 0), int(data.get("likes", 0)))
        post.comments = max(int(post.comments or 0), int(data.get("comments", 0)))
        post.views = max(int(post.views or 0), int(data.get("views", 0)))
        filled += 1
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)
    logger.info(
        "polaris enrich @%s filled=%s/%s", username, filled, len(targets)
    )
    return filled
