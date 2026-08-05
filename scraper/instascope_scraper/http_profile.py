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
    timeout = httpx.Timeout(30.0)
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, proxy=proxy, timeout=timeout) as client:
        await _bootstrap_session(client, username)
        headers = _client_headers(username)
        _apply_csrf(client, headers)
        res = await client.get(url, headers=headers)
        if res.status_code != 200:
            logger.warning("web_profile_info %s → HTTP %s", username, res.status_code)
            return None
        try:
            return res.json()
        except Exception:
            return None


def _timeline_from_user(user: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None, bool]:
    """Return (edge nodes, end_cursor, has_next_page)."""
    media = user.get("edge_owner_to_timeline_media") or {}
    edges = media.get("edges") or []
    nodes: list[dict[str, Any]] = []
    for edge in edges:
        node = edge.get("node") if isinstance(edge, dict) else None
        if isinstance(node, dict):
            nodes.append(node)
    page = media.get("page_info") or {}
    cursor = page.get("end_cursor")
    has_next = bool(page.get("has_next_page"))
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
    res = await client.get(url, headers=headers)
    if res.status_code != 200:
        logger.debug("feed/user %s max_id=%s → HTTP %s", user_id, max_id, res.status_code)
        return None
    try:
        payload = res.json()
    except Exception:
        return None
    if payload.get("status") == "fail":
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

    next_max = payload.get("next_max_id") or payload.get("max_id")
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
        # Full-ish page with a cursor ⇒ assume more exists until proven otherwise
        more = bool(cursor) and len(nodes) >= 1
    else:
        more = bool(more_flag)
        if not more and cursor and len(nodes) >= 12:
            # IG sometimes lies with more_available=false on page 1 — keep going if cursor present
            more = True

    return nodes, cursor, more


def _node_key(node: dict[str, Any]) -> str:
    return str(node.get("shortcode") or node.get("code") or node.get("id") or node.get("pk") or "")


def _still_short(collected: int, *, limit: int, expected_count: int) -> bool:
    if collected >= limit:
        return False
    if expected_count > 0:
        return collected < max(expected_count - 2, 1)
    # Unknown total: first profile card (~12) is never "done"
    return collected <= 12


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
                feed = await _feed_user_page(
                    client,
                    username=username,
                    user_id=user_id,
                    max_id=max_id,
                    count=page_size,
                    mobile=use_mobile,
                )
                if not feed:
                    if pages == 1 and not use_mobile:
                        alt = await _feed_user_page_username(
                            client,
                            username=username,
                            max_id=max_id,
                            count=page_size,
                        )
                        if alt:
                            feed = alt
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
                        continue
                    break

                added = _add(nodes)
                if added == 0:
                    stagnant += 1
                    # Page-1 returned the same seed cards — jump using last media id
                    if not tried_seed_jump and feed_seed_cursor and max_id != feed_seed_cursor:
                        max_id = feed_seed_cursor
                        tried_seed_jump = True
                        stagnant = 0
                        more = True
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
                        more = False
                else:
                    more = False

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


async def _feed_user_page_username(
    client: httpx.AsyncClient,
    *,
    username: str,
    max_id: str | None,
    count: int,
) -> dict[str, Any] | None:
    """Alternate feed path: /api/v1/feed/user/{username}/username/."""
    q = f"count={count}"
    if max_id:
        q += f"&max_id={quote(str(max_id))}"
    url = f"https://www.instagram.com/api/v1/feed/user/{quote(username)}/username/?{q}"
    headers = _client_headers(username)
    _apply_csrf(client, headers)
    res = await client.get(url, headers=headers)
    if res.status_code != 200:
        return None
    try:
        payload = res.json()
    except Exception:
        return None
    if payload.get("status") == "fail":
        return None
    return payload
