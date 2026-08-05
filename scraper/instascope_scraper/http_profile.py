"""HTTP Instagram profile + paginated media fetch (real data).

Fetches the full public timeline (not just the first ~12 profile-card posts).
SCRAPE_MAX_POSTS=0 means all posts (hard safety cap 50_000).

Primary pagination uses /api/v1/feed/user/{id}/ (Instagram web's current path).
Legacy GraphQL query_hash is a fallback only — Meta rotates those frequently.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any
from urllib.parse import quote

import httpx

logger = logging.getLogger("instascope.scraper.http_profile")

IG_APP_ID = "936619743392459"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
# Mobile app UA — feed endpoint is more reliable with this.
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Mobile/15E148 Instagram 312.0.0.0.0"
)

# Legacy GraphQL identifiers (often dead; kept as last resort).
TIMELINE_QUERY_HASHES = (
    "e769aa130647d2354c40ea6a439bfc08",
    "42323d64886122307be10013ad2dcc44",
    "69cba40317214287afd42f5a24efd3f5",
    "56a7068fea504063273cc2120ffd54f3",
)
TIMELINE_QUERY_IDS = (
    "17842794232208280",
)
# Polaris / RelayModern doc_ids for profile media (rotate often).
TIMELINE_DOC_IDS = (
    "7950326061742207",
    "7898261790222653",
    "24322560968800747",
)


def _max_posts() -> int:
    """0 / unset = fetch all (hard safety cap 50_000)."""
    raw = (os.getenv("SCRAPE_MAX_POSTS") or "0").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 0
    if n <= 0:
        return 50_000
    return min(n, 50_000)


def _page_size() -> int:
    try:
        n = int(os.getenv("SCRAPE_POSTS_PAGE_SIZE") or "12")
    except ValueError:
        n = 12
    # Feed API is most stable at 12; larger counts often get silently truncated.
    return max(12, min(n, 12))


def _client_headers(username: str) -> dict[str, str]:
    return {
        "User-Agent": UA,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "X-IG-App-ID": IG_APP_ID,
        "X-ASBD-ID": "129477",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"https://www.instagram.com/{username}/",
        "Origin": "https://www.instagram.com",
    }


async def _get_json_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str],
    label: str,
    max_retries: int | None = None,
) -> tuple[int, dict[str, Any] | None, str]:
    """GET JSON with retries on 429 / 5xx. Returns (status, payload|None, body_snip)."""
    if max_retries is None:
        max_retries = max(1, int(os.getenv("SCRAPE_HTTP_RETRIES") or "5"))
    last_status = 0
    last_snip = ""
    for attempt in range(max_retries):
        try:
            res = await client.get(url, headers=headers)
        except Exception:
            logger.exception("%s GET failed attempt=%s url=%s", label, attempt + 1, url[:160])
            if attempt + 1 >= max_retries:
                raise
            await asyncio.sleep(1.5 * (attempt + 1))
            continue
        last_status = res.status_code
        last_snip = (res.text or "")[:300]
        if res.status_code == 200:
            try:
                return res.status_code, res.json(), last_snip
            except Exception:
                logger.exception("%s JSON parse failed url=%s snip=%r", label, url[:160], last_snip)
                return res.status_code, None, last_snip
        # Instagram rate-limit often returns 401/403 with "Please wait a few minutes"
        # rather than 429 — treat those as retriable.
        retriable = res.status_code in {429, 500, 502, 503, 504}
        if res.status_code in {401, 403}:
            low = last_snip.lower()
            if "please wait" in low or "rate" in low or "try again" in low:
                retriable = True
        if retriable:
            wait = min(60.0, (2 ** attempt) * 1.5)
            # Honor Retry-After when present
            ra = res.headers.get("Retry-After")
            if ra:
                try:
                    wait = max(wait, float(ra))
                except ValueError:
                    pass
            logger.warning(
                "%s HTTP %s attempt=%s/%s wait=%.1fs url=%s body=%r",
                label,
                res.status_code,
                attempt + 1,
                max_retries,
                wait,
                url[:160],
                last_snip[:180],
            )
            await asyncio.sleep(wait)
            continue
        logger.warning(
            "%s HTTP %s (no retry) url=%s body=%r",
            label,
            res.status_code,
            url[:160],
            last_snip[:180],
        )
        return res.status_code, None, last_snip
    return last_status, None, last_snip


def _csrf_from_cookies(client: httpx.AsyncClient) -> str | None:
    for cookie in client.cookies.jar:
        if cookie.name.lower() == "csrftoken" and cookie.value:
            return cookie.value
    return None


def _apply_csrf(client: httpx.AsyncClient, headers: dict[str, str]) -> None:
    token = _csrf_from_cookies(client)
    if token:
        headers["X-CSRFToken"] = token
        headers["X-IG-WWW-Claim"] = "0"


async def _bootstrap_session(client: httpx.AsyncClient, username: str) -> None:
    """Visit Instagram so we get csrftoken / mid cookies before API calls."""
    await client.get("https://www.instagram.com/")
    await client.get(f"https://www.instagram.com/{username}/")
    _apply_csrf(client, dict(client.headers))


async def fetch_web_profile_http(username: str, *, proxy: str | None = None) -> dict[str, Any] | None:
    headers = _client_headers(username)
    url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
    timeout = httpx.Timeout(45.0)
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, proxy=proxy, timeout=timeout) as client:
        await _bootstrap_session(client, username)
        headers = _client_headers(username)
        _apply_csrf(client, headers)
        status, payload, snip = await _get_json_with_retry(
            client,
            url,
            headers=headers,
            label=f"web_profile_info @{username}",
            # Fail fast on sustained 401 Please wait — username feed is the recovery path
            max_retries=max(1, int(os.getenv("SCRAPE_WEB_PROFILE_RETRIES") or "2")),
        )
        if status != 200 or not payload:
            logger.warning("web_profile_info @%s → HTTP %s body=%r", username, status, snip[:180])
            return None
        return payload


def _timeline_from_user(user: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None, bool]:
    """Return (edge nodes, end_cursor, has_next_page) from posts + reels edges."""
    nodes: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add_edges(media: Any) -> tuple[str | None, bool]:
        if not isinstance(media, dict):
            return None, False
        for edge in media.get("edges") or []:
            node = edge.get("node") if isinstance(edge, dict) else None
            if not isinstance(node, dict):
                continue
            key = _node_key(node)
            if not key or key in seen:
                continue
            seen.add(key)
            nodes.append(node)
        page = media.get("page_info") or {}
        return page.get("end_cursor"), bool(page.get("has_next_page"))

    cursor, has_next = _add_edges(user.get("edge_owner_to_timeline_media"))
    felix_cursor, felix_next = _add_edges(user.get("edge_felix_video_timeline"))
    if not cursor:
        cursor = felix_cursor
    has_next = has_next or felix_next

    # Newer shapes
    for key in ("media", "reel"):
        media = user.get(key) or {}
        if not isinstance(media, dict):
            continue
        for node in media.get("nodes") or media.get("items") or []:
            if not isinstance(node, dict):
                continue
            nk = _node_key(node)
            if not nk or nk in seen:
                continue
            seen.add(nk)
            nodes.append(node)

    return nodes, cursor, has_next


async def _graphql_timeline_page(
    client: httpx.AsyncClient,
    *,
    username: str,
    user_id: str,
    after: str | None,
    first: int,
    query_hash: str | None = None,
    query_id: str | None = None,
) -> dict[str, Any] | None:
    variables = {"id": user_id, "first": first}
    if after:
        variables["after"] = after
    encoded = quote(json.dumps(variables, separators=(",", ":")))
    if query_hash:
        url = f"https://www.instagram.com/graphql/query/?query_hash={query_hash}&variables={encoded}"
    elif query_id:
        url = f"https://www.instagram.com/graphql/query/?query_id={query_id}&variables={encoded}"
    else:
        return None
    headers = _client_headers(username)
    _apply_csrf(client, headers)
    res = await client.get(url, headers=headers)
    if res.status_code != 200:
        return None
    try:
        return res.json()
    except Exception:
        return None


async def _doc_id_timeline_page(
    client: httpx.AsyncClient,
    *,
    username: str,
    user_id: str,
    after: str | None,
    first: int,
    doc_id: str,
) -> dict[str, Any] | None:
    """POST RelayModern/doc_id GraphQL (current Instagram web style)."""
    variables: dict[str, Any] = {"id": user_id, "first": first}
    if after:
        variables["after"] = after
    # Alternate Polaris shape used by some doc_ids
    alt_variables = {
        "data": {"count": first, "include_relationship_info": True},
        "username": username,
    }
    if after:
        alt_variables["data"]["max_id"] = after  # type: ignore[index]

    headers = _client_headers(username)
    headers["Content-Type"] = "application/x-www-form-urlencoded"
    _apply_csrf(client, headers)

    for vars_payload in (variables, alt_variables):
        data = {
            "variables": json.dumps(vars_payload, separators=(",", ":")),
            "doc_id": doc_id,
            "server_timestamps": "true",
        }
        res = await client.post("https://www.instagram.com/graphql/query", headers=headers, data=data)
        if res.status_code != 200:
            continue
        try:
            payload = res.json()
        except Exception:
            continue
        if payload.get("data"):
            return payload
    return None


async def _feed_user_page(
    client: httpx.AsyncClient,
    *,
    username: str,
    user_id: str,
    max_id: str | None,
    count: int,
    mobile: bool = False,
) -> dict[str, Any] | None:
    """Paginate via /api/v1/feed/user/{id}/ (preferred path in 2025–2026)."""
    q = f"count={count}"
    if max_id:
        q += f"&max_id={quote(str(max_id))}"
    host = "i.instagram.com" if mobile else "www.instagram.com"
    url = f"https://{host}/api/v1/feed/user/{user_id}/?{q}"
    headers = _client_headers(username)
    if mobile:
        headers["User-Agent"] = MOBILE_UA
        headers["X-IG-App-ID"] = IG_APP_ID
    _apply_csrf(client, headers)
    label = f"feed/user_id @{username} mobile={mobile}"
    status, payload, snip = await _get_json_with_retry(client, url, headers=headers, label=label)
    if status != 200 or not payload:
        logger.info("%s max_id=%s → HTTP %s body=%r", label, max_id, status, snip[:160])
        return None
    if payload.get("status") == "fail":
        logger.warning("%s status=fail message=%r", label, payload.get("message"))
        return None
    return payload


def _normalize_cursor(value: Any) -> str | None:
    """Coerce Instagram pagination cursors (str / int / nested / JSON string)."""
    if value is None or value is False:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return str(int(value))
    if isinstance(value, str):
        text = value.strip()
        if not text or text.lower() in {"null", "none", "undefined"}:
            return None
        if text.startswith("{") and "max_id" in text:
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    nested = parsed.get("max_id") or parsed.get("next_max_id")
                    if nested is not None:
                        return _normalize_cursor(nested)
            except Exception:
                pass
        return text
    if isinstance(value, dict):
        for key in ("max_id", "next_max_id", "end_cursor", "cursor", "id", "pk"):
            if key in value and value[key] is not None:
                found = _normalize_cursor(value[key])
                if found:
                    return found
    return None


def _cursor_from_node(node: dict[str, Any]) -> str | None:
    """Fallback cursor = last media id (Instagram accepts pk/id as max_id)."""
    for key in ("id", "pk", "pk_id", "media_id"):
        raw = node.get(key)
        if raw is None:
            continue
        # Prefer bare numeric id when shape is "12345_67890"
        text = str(raw).strip()
        if "_" in text:
            text = text.split("_", 1)[0]
        if text:
            return text
    return None


def _nodes_from_feed(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None, bool]:
    items = payload.get("items") or []
    if not isinstance(items, list):
        items = []
    nodes = [it for it in items if isinstance(it, dict)]

    # Newer web responses may put media under profile_grid_items[].media
    if not nodes:
        for entry in payload.get("profile_grid_items") or []:
            if not isinstance(entry, dict):
                continue
            media = entry.get("media") if isinstance(entry.get("media"), dict) else entry
            if isinstance(media, dict) and (media.get("code") or media.get("pk") or media.get("id")):
                nodes.append(media)

    next_max = (
        payload.get("next_max_id")
        or payload.get("max_id")
        or payload.get("profile_grid_items_cursor")
    )
    paging = payload.get("paging_info")
    if next_max is None and isinstance(paging, dict):
        next_max = paging.get("max_id") or paging.get("next_max_id")
    # next_max_id may live on the last item in some app responses
    if next_max is None and nodes:
        last = nodes[-1]
        next_max = last.get("next_max_id")

    cursor = _normalize_cursor(next_max)
    if not cursor and nodes:
        cursor = _cursor_from_node(nodes[-1])

    more_flag = payload.get("more_available")
    if more_flag is None:
        # Any page with a cursor ⇒ assume more until proven otherwise
        more = bool(cursor) and len(nodes) >= 1
    else:
        more = bool(more_flag)
        # IG often lies with more_available=false while next_max_id is present —
        # keep going whenever a cursor exists (critical for small accounts < 12).
        if not more and cursor and len(nodes) >= 1:
            more = True

    return nodes, cursor, more


def _node_key(node: dict[str, Any]) -> str:
    return str(node.get("shortcode") or node.get("code") or node.get("id") or node.get("pk") or "")


def _still_short(collected: int, *, limit: int, expected_count: int) -> bool:
    """True when we must keep paginating toward Instagram's posts_count."""
    if collected >= limit:
        return False
    if expected_count > 0:
        # Small accounts: require every post (2/6 must keep going).
        # Large accounts: allow 1–2 deleted/hidden drift.
        if expected_count <= 12:
            return collected < expected_count
        return collected < max(expected_count - 2, 1)
    # Unknown total: keep going past the first card — caller stops on more_available=false
    return True


async def fetch_all_media_nodes(
    username: str,
    *,
    user_id: str,
    initial_nodes: list[dict[str, Any]] | None = None,
    initial_cursor: str | None = None,
    initial_has_next: bool = False,
    expected_count: int = 0,
    proxy: str | None = None,
) -> list[dict[str, Any]]:
    """Paginate until all (or SCRAPE_MAX_POSTS) timeline media nodes are collected."""
    limit = _max_posts()
    if expected_count > 0:
        limit = min(limit, expected_count)
    page_size = _page_size()
    delay = float(os.getenv("SCRAPE_PAGE_DELAY_SECONDS") or "0.8")

    seen: set[str] = set()
    out: list[dict[str, Any]] = []

    def _add(nodes: list[dict[str, Any]]) -> int:
        added = 0
        for node in nodes:
            key = _node_key(node)
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(node)
            added += 1
            if len(out) >= limit:
                break
        return added

    _add(initial_nodes or [])
    if len(out) >= limit:
        return out[:limit]

    # Feed API wants media id/pk as max_id — NOT GraphQL end_cursor
    feed_seed_cursor = _cursor_from_node(out[-1]) if out else None
    graphql_cursor = _normalize_cursor(initial_cursor)

    headers = _client_headers(username)
    timeout = httpx.Timeout(60.0)
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, proxy=proxy, timeout=timeout) as client:
        await _bootstrap_session(client, username)

        # --- 1) Feed API (www, then mobile) — keep paging until full timeline ---
        for use_mobile in (False, True):
            if not _still_short(len(out), limit=limit, expected_count=expected_count):
                break

            max_id: str | None = None
            more = True
            stagnant = 0
            pages = 0
            max_pages = max(60, (limit // max(page_size, 1)) + 80)
            # Prefer discovering next_max_id from a fresh page-1 call.
            # If that returns only duplicates, advance using last seed media id.
            tried_seed_jump = False

            while more and _still_short(len(out), limit=limit, expected_count=expected_count) and stagnant < 10 and pages < max_pages:
                pages += 1
                await asyncio.sleep(delay if pages > 1 else 0.15)

                # Prefer username feed first — user_id feed often returns 401 anonymously
                feed = None
                if not use_mobile:
                    feed = await _feed_user_page_username(
                        client,
                        username=username,
                        max_id=max_id,
                        count=page_size,
                    )
                if not feed:
                    feed = await _feed_user_page(
                        client,
                        username=username,
                        user_id=user_id,
                        max_id=max_id,
                        count=page_size,
                        mobile=use_mobile,
                    )
                if not feed:
                    stagnant += 1
                    if max_id is None and feed_seed_cursor:
                        max_id = feed_seed_cursor
                        continue
                    break

                nodes, next_cursor, more = _nodes_from_feed(feed)
                if not nodes:
                    stagnant += 1
                    if next_cursor and next_cursor != max_id:
                        max_id = next_cursor
                        more = True
                        continue
                    if max_id is None and feed_seed_cursor:
                        max_id = feed_seed_cursor
                        more = True
                        continue
                    break

                added = _add(nodes)
                logger.info(
                    "feed page @%s mobile=%s page=%s max_id=%s got=%s added=%s total=%s "
                    "next=%s more=%s expected=%s",
                    username,
                    use_mobile,
                    pages,
                    max_id,
                    len(nodes),
                    added,
                    len(out),
                    next_cursor,
                    more,
                    expected_count,
                )
                if added == 0:
                    stagnant += 1
                    # Prefer Instagram's next_max_id from this response — do NOT discard it
                    # for a bare pk seed jump (that was discarding a working cursor).
                    if next_cursor and next_cursor != max_id:
                        max_id = next_cursor
                        feed_seed_cursor = next_cursor
                        more = True
                        logger.info(
                            "feed @%s duplicate page — advancing via next_max_id=%s",
                            username,
                            max_id,
                        )
                        continue
                    if not tried_seed_jump and feed_seed_cursor and max_id != feed_seed_cursor:
                        max_id = feed_seed_cursor
                        tried_seed_jump = True
                        stagnant = 0
                        more = True
                        logger.info(
                            "feed @%s duplicate page — seed jump max_id=%s",
                            username,
                            max_id,
                        )
                        continue
                else:
                    stagnant = 0

                if next_cursor and next_cursor != max_id:
                    max_id = next_cursor
                    feed_seed_cursor = next_cursor
                elif nodes:
                    derived = _cursor_from_node(nodes[-1])
                    if derived and derived != max_id:
                        max_id = derived
                        more = more or _still_short(len(out), limit=limit, expected_count=expected_count)
                    else:
                        # No cursor but we may still be short — force seed jump once
                        if not tried_seed_jump and feed_seed_cursor and expected_count > len(out):
                            max_id = feed_seed_cursor
                            tried_seed_jump = True
                            more = True
                            stagnant = 0
                            continue
                        more = False
                else:
                    more = False

                # Never stop early while Instagram says we should have more posts
                if (
                    not more
                    and _still_short(len(out), limit=limit, expected_count=expected_count)
                    and (next_cursor or max_id or feed_seed_cursor)
                ):
                    more = True
                    if next_cursor:
                        max_id = next_cursor
                    elif not max_id and feed_seed_cursor:
                        max_id = feed_seed_cursor

                if expected_count > 0 and len(out) >= expected_count:
                    break

            logger.info(
                "feed pagination @%s mobile=%s collected=%s expected=%s pages=%s",
                username,
                use_mobile,
                len(out),
                expected_count,
                pages,
            )

        # --- 2) doc_id GraphQL POST (run whenever still short — including exactly 12) ---
        need_more = _still_short(len(out), limit=limit, expected_count=expected_count)
        if need_more:
            cursor = graphql_cursor or (_cursor_from_node(out[-1]) if out else None)
            has_next = initial_has_next or bool(cursor) or need_more
            working_doc: str | None = None
            stagnant = 0
            pages = 0
            while has_next and need_more and cursor and stagnant < 5 and pages < 80:
                pages += 1
                need_more = _still_short(len(out), limit=limit, expected_count=expected_count)
                await asyncio.sleep(delay)
                payload: dict[str, Any] | None = None
                if working_doc:
                    payload = await _doc_id_timeline_page(
                        client,
                        username=username,
                        user_id=user_id,
                        after=cursor,
                        first=page_size,
                        doc_id=working_doc,
                    )
                else:
                    for doc_id in TIMELINE_DOC_IDS:
                        payload = await _doc_id_timeline_page(
                            client,
                            username=username,
                            user_id=user_id,
                            after=cursor,
                            first=page_size,
                            doc_id=doc_id,
                        )
                        if payload and (payload.get("data") or {}).get("user"):
                            working_doc = doc_id
                            break
                        data = payload.get("data") if payload else None
                        if isinstance(data, dict) and data:
                            working_doc = doc_id
                            break
                        payload = None
                if not payload:
                    break
                user = (payload.get("data") or {}).get("user") or {}
                if not user:
                    data = payload.get("data") or {}
                    for v in data.values():
                        if isinstance(v, dict) and "edge_owner_to_timeline_media" in v:
                            user = v
                            break
                nodes, cursor, has_next = _timeline_from_user(user) if user else ([], None, False)
                cursor = _normalize_cursor(cursor)
                if not nodes:
                    stagnant += 1
                    continue
                added = _add(nodes)
                stagnant = 0 if added else stagnant + 1
                if not cursor:
                    has_next = False
                need_more = _still_short(len(out), limit=limit, expected_count=expected_count)

        # --- 3) Legacy query_hash / query_id ---
        need_more = _still_short(len(out), limit=limit, expected_count=expected_count)
        if need_more:
            cursor = graphql_cursor or (_cursor_from_node(out[-1]) if out else None)
            has_next = initial_has_next or bool(cursor) or need_more
            working_hash: str | None = None
            working_qid: str | None = None
            pages = 0
            while has_next and need_more and cursor and pages < 80:
                pages += 1
                need_more = _still_short(len(out), limit=limit, expected_count=expected_count)
                await asyncio.sleep(delay)
                payload = None
                if working_hash:
                    payload = await _graphql_timeline_page(
                        client,
                        username=username,
                        user_id=user_id,
                        after=cursor,
                        first=page_size,
                        query_hash=working_hash,
                    )
                elif working_qid:
                    payload = await _graphql_timeline_page(
                        client,
                        username=username,
                        user_id=user_id,
                        after=cursor,
                        first=page_size,
                        query_id=working_qid,
                    )
                else:
                    for qh in TIMELINE_QUERY_HASHES:
                        payload = await _graphql_timeline_page(
                            client,
                            username=username,
                            user_id=user_id,
                            after=cursor,
                            first=page_size,
                            query_hash=qh,
                        )
                        if payload and (payload.get("data") or {}).get("user"):
                            working_hash = qh
                            break
                        payload = None
                    if not payload:
                        for qid in TIMELINE_QUERY_IDS:
                            payload = await _graphql_timeline_page(
                                client,
                                username=username,
                                user_id=user_id,
                                after=cursor,
                                first=page_size,
                                query_id=qid,
                            )
                            if payload and (payload.get("data") or {}).get("user"):
                                working_qid = qid
                                break
                            payload = None
                if not payload:
                    break
                user = (payload.get("data") or {}).get("user") or {}
                nodes, cursor, has_next = _timeline_from_user(user)
                cursor = _normalize_cursor(cursor)
                if not nodes:
                    break
                _add(nodes)
                if not cursor:
                    has_next = False

    logger.info(
        "fetch_all_media_nodes @%s done collected=%s expected=%s limit=%s",
        username,
        len(out),
        expected_count,
        limit,
    )
    return out[:limit]


async def fetch_timeline_via_username_feed(
    username: str,
    *,
    expected_count: int = 0,
    proxy: str | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Paginate the full timeline using only /feed/user/{username}/username/.

    Works when web_profile_info is rate-limited (401 Please wait). The first feed
    page often includes a `user` object with id + media_count.
    """
    headers = _client_headers(username)
    timeout = httpx.Timeout(60.0)
    user_obj: dict[str, Any] | None = None
    nodes: list[dict[str, Any]] = []
    seen: set[str] = set()
    limit = _max_posts()
    if expected_count > 0:
        limit = min(limit, expected_count)
    page_size = _page_size()
    delay = float(os.getenv("SCRAPE_PAGE_DELAY_SECONDS") or "0.8")

    async with httpx.AsyncClient(headers=headers, follow_redirects=True, proxy=proxy, timeout=timeout) as client:
        await _bootstrap_session(client, username)
        max_id: str | None = None
        more = True
        stagnant = 0
        pages = 0
        max_pages = max(80, (limit // max(page_size, 1)) + 40)

        while more and _still_short(len(nodes), limit=limit, expected_count=expected_count) and stagnant < 10 and pages < max_pages:
            pages += 1
            if pages > 1:
                await asyncio.sleep(delay)
            feed = await _feed_user_page_username(
                client, username=username, max_id=max_id, count=page_size
            )
            if not feed:
                stagnant += 1
                logger.warning(
                    "username_feed @%s page=%s failed stagnant=%s max_id=%s",
                    username,
                    pages,
                    stagnant,
                    max_id,
                )
                continue

            if user_obj is None:
                raw_user = feed.get("user")
                if isinstance(raw_user, dict):
                    user_obj = raw_user
                    if expected_count <= 0:
                        expected_count = _parse_media_count(raw_user)
                        if expected_count > 0:
                            limit = min(_max_posts(), expected_count)

            page_nodes, next_cursor, more = _nodes_from_feed(feed)
            added = 0
            for node in page_nodes:
                key = _node_key(node)
                if not key or key in seen:
                    continue
                seen.add(key)
                nodes.append(node)
                added += 1
                if len(nodes) >= limit:
                    break

            logger.info(
                "username_feed @%s page=%s got=%s added=%s total=%s next=%s more=%s expected=%s",
                username,
                pages,
                len(page_nodes),
                added,
                len(nodes),
                next_cursor,
                more,
                expected_count,
            )

            if added == 0:
                stagnant += 1
                if next_cursor and next_cursor != max_id:
                    max_id = next_cursor
                    more = True
                    continue
                if not more:
                    break
            else:
                stagnant = 0

            if next_cursor and next_cursor != max_id:
                max_id = next_cursor
            elif page_nodes:
                derived = _cursor_from_node(page_nodes[-1])
                if derived and derived != max_id:
                    max_id = derived
                    more = more or _still_short(len(nodes), limit=limit, expected_count=expected_count)
                else:
                    more = False
            else:
                more = False

            if expected_count > 0 and len(nodes) >= expected_count:
                break

    logger.info(
        "username_feed @%s done collected=%s expected=%s user=%s",
        username,
        len(nodes),
        expected_count,
        bool(user_obj),
    )
    return user_obj, nodes[:limit]


def _parse_media_count(user: dict[str, Any]) -> int:
    for key in ("media_count", "posts_count", "total_clips_count"):
        raw = user.get(key)
        if raw is None:
            continue
        try:
            return int(raw)
        except (TypeError, ValueError):
            continue
    edge = user.get("edge_owner_to_timeline_media")
    if isinstance(edge, dict) and edge.get("count") is not None:
        try:
            return int(edge["count"])
        except (TypeError, ValueError):
            pass
    return 0


async def _feed_user_page_username(
    client: httpx.AsyncClient,
    *,
    username: str,
    max_id: str | None,
    count: int,
) -> dict[str, Any] | None:
    """Primary anonymous feed path: /api/v1/feed/user/{username}/username/.

    Empirically more reliable than /feed/user/{id}/ which returns 401 require_login
    for anonymous sessions. Supports pagination via next_max_id.
    """
    q = f"count={count}"
    if max_id:
        q += f"&max_id={quote(str(max_id))}"
    url = f"https://www.instagram.com/api/v1/feed/user/{quote(username)}/username/?{q}"
    headers = _client_headers(username)
    _apply_csrf(client, headers)
    label = f"feed/username @{username}"
    status, payload, snip = await _get_json_with_retry(client, url, headers=headers, label=label)
    if status != 200 or not payload:
        logger.info("%s max_id=%s → HTTP %s body=%r", label, max_id, status, snip[:160])
        return None
    if payload.get("status") == "fail":
        logger.warning("%s status=fail message=%r", label, payload.get("message"))
        return None
    return payload
