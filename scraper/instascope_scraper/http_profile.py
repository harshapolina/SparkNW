"""HTTP Instagram profile + paginated media fetch (real data).

Fetches the full public timeline (not just the first ~12 profile-card posts).
SCRAPE_MAX_POSTS=0 means all posts (hard safety cap 50_000).
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any
from urllib.parse import quote

import httpx


IG_APP_ID = "936619743392459"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

# Instagram rotates hashes; try several known timeline query identifiers.
TIMELINE_QUERY_HASHES = (
    "e769aa130647d2354c40ea6a439bfc08",
    "42323d64886122307be10013ad2dcc44",
    "69cba40317214287afd42f5a24efd3f5",
)
TIMELINE_QUERY_IDS = (
    "17842794232208280",
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
        n = int(os.getenv("SCRAPE_POSTS_PAGE_SIZE") or "50")
    except ValueError:
        n = 50
    # Instagram often rejects >50; 12 is the historical page size.
    return max(12, min(n, 50))


def _client_headers(username: str) -> dict[str, str]:
    return {
        "User-Agent": UA,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "X-IG-App-ID": IG_APP_ID,
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"https://www.instagram.com/{username}/",
        "Origin": "https://www.instagram.com",
    }


async def fetch_web_profile_http(username: str, *, proxy: str | None = None) -> dict[str, Any] | None:
    headers = _client_headers(username)
    url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
    timeout = httpx.Timeout(30.0)
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, proxy=proxy, timeout=timeout) as client:
        await client.get(f"https://www.instagram.com/{username}/")
        res = await client.get(url)
        if res.status_code != 200:
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
    res = await client.get(url)
    if res.status_code != 200:
        return None
    try:
        return res.json()
    except Exception:
        return None


async def _feed_user_page(
    client: httpx.AsyncClient,
    *,
    user_id: str,
    max_id: str | None,
    count: int,
) -> dict[str, Any] | None:
    """Fallback: mobile web feed endpoint."""
    q = f"count={count}"
    if max_id:
        q += f"&max_id={quote(str(max_id))}"
    url = f"https://www.instagram.com/api/v1/feed/user/{user_id}/?{q}"
    res = await client.get(url)
    if res.status_code != 200:
        return None
    try:
        return res.json()
    except Exception:
        return None


def _nodes_from_feed(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None, bool]:
    items = payload.get("items") or []
    nodes = [it for it in items if isinstance(it, dict)]
    more = bool(payload.get("more_available"))
    next_max = payload.get("next_max_id")
    return nodes, str(next_max) if next_max is not None else None, more


def _node_key(node: dict[str, Any]) -> str:
    return str(node.get("shortcode") or node.get("code") or node.get("id") or node.get("pk") or "")


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
    delay = float(os.getenv("SCRAPE_PAGE_DELAY_SECONDS") or "0.6")

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
        return added

    _add(initial_nodes or [])
    if len(out) >= limit:
        return out[:limit]

    headers = _client_headers(username)
    timeout = httpx.Timeout(45.0)
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, proxy=proxy, timeout=timeout) as client:
        await client.get(f"https://www.instagram.com/{username}/")

        # --- GraphQL cursor pagination (try multiple query identifiers) ---
        cursor = initial_cursor
        has_next = initial_has_next or bool(cursor)
        working_hash: str | None = None
        working_qid: str | None = None

        while has_next and len(out) < limit and cursor:
            await asyncio.sleep(delay)
            payload: dict[str, Any] | None = None

            if working_hash:
                payload = await _graphql_timeline_page(
                    client, user_id=user_id, after=cursor, first=page_size, query_hash=working_hash
                )
            elif working_qid:
                payload = await _graphql_timeline_page(
                    client, user_id=user_id, after=cursor, first=page_size, query_id=working_qid
                )
            else:
                for qh in TIMELINE_QUERY_HASHES:
                    payload = await _graphql_timeline_page(
                        client, user_id=user_id, after=cursor, first=page_size, query_hash=qh
                    )
                    if payload and (payload.get("data") or {}).get("user"):
                        working_hash = qh
                        break
                    payload = None
                if not payload:
                    for qid in TIMELINE_QUERY_IDS:
                        payload = await _graphql_timeline_page(
                            client, user_id=user_id, after=cursor, first=page_size, query_id=qid
                        )
                        if payload and (payload.get("data") or {}).get("user"):
                            working_qid = qid
                            break
                        payload = None

            if not payload:
                break
            user = (payload.get("data") or {}).get("user") or {}
            nodes, cursor, has_next = _timeline_from_user(user)
            if not nodes:
                break
            _add(nodes)

        # --- Feed API: always fill the gap if we're still short of the profile total ---
        need_more = len(out) < limit and (expected_count <= 0 or len(out) < expected_count)
        if need_more:
            max_id: str | None = None
            more = True
            seen_max_ids: set[str] = set()
            while more and len(out) < limit:
                if max_id in seen_max_ids:
                    break
                if max_id:
                    seen_max_ids.add(max_id)
                await asyncio.sleep(delay)
                feed = await _feed_user_page(client, user_id=user_id, max_id=max_id, count=page_size)
                if not feed:
                    break
                nodes, max_id, more = _nodes_from_feed(feed)
                if not nodes:
                    break
                _add(nodes)
                if not max_id:
                    break
                if expected_count > 0 and len(out) >= expected_count:
                    break

    return out[:limit]
