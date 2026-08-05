"""Diagnose Instagram feed pagination — why scrapes stop at ~12 posts."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scraper"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


async def diagnose(username: str) -> None:
    import httpx
    from instascope_scraper.http_profile import (
        _apply_csrf,
        _bootstrap_session,
        _client_headers,
        _cursor_from_node,
        _feed_user_page,
        _feed_user_page_username,
        _nodes_from_feed,
        _page_size,
        fetch_web_profile_http,
    )

    uname = username.lstrip("@").strip().lower()
    print(f"\n======== DIAGNOSE @{uname} ========")
    print(f"SCRAPE_PROXY_URL set: {bool(os.getenv('SCRAPE_PROXY_URL'))}")
    print(f"page_size={_page_size()}")

    proxy = None
    headers = _client_headers(uname)
    timeout = httpx.Timeout(45.0)

    async with httpx.AsyncClient(headers=headers, follow_redirects=True, proxy=proxy, timeout=timeout) as client:
        print("\n--- bootstrap session ---")
        try:
            await _bootstrap_session(client, uname)
            print(f"cookies: {[c.name for c in client.cookies.jar]}")
        except Exception:
            traceback.print_exc()

        print("\n--- web_profile_info ---")
        payload = await fetch_web_profile_http(uname, proxy=proxy)
        if not payload:
            print("FAILED: no web_profile_info")
            return
        user = (payload.get("data") or {}).get("user") or {}
        uid = str(user.get("id") or user.get("pk") or "")
        media = user.get("edge_owner_to_timeline_media") or {}
        count = media.get("count") or user.get("media_count")
        edges = media.get("edges") or []
        page_info = media.get("page_info") or {}
        print(f"user_id={uid} posts_count={count} initial_edges={len(edges)}")
        print(f"page_info={json.dumps(page_info)[:300]}")
        print(f"is_private={user.get('is_private')}")

        if edges:
            first = edges[0].get("node") or {}
            last = edges[-1].get("node") or {}
            print(f"first_code={first.get('shortcode')} last_code={last.get('shortcode')} last_id={last.get('id')}")

        end_cursor = page_info.get("end_cursor")
        has_next = page_info.get("has_next_page")
        print(f"graphql end_cursor present={bool(end_cursor)} has_next_page={has_next}")

        # Feed page 1 (no max_id)
        print("\n--- feed page 1 (username path, no max_id) ---")
        feed1 = await _feed_user_page_username(client, username=uname, max_id=None, count=12)
        if feed1:
            nodes, cursor, more = _nodes_from_feed(feed1)
            print(f"items={len(nodes)} next_max_id={feed1.get('next_max_id')!r}")
            print(f"more_available={feed1.get('more_available')!r} derived_more={more} derived_cursor={cursor!r}")
            print(f"status={feed1.get('status')} keys={list(feed1.keys())[:20]}")
            if nodes:
                print(f"last_pk={nodes[-1].get('pk') or nodes[-1].get('id')}")
        else:
            print("FAILED username feed page 1")
            # raw status
            url = f"https://www.instagram.com/api/v1/feed/user/{uname}/username/?count=12"
            h = _client_headers(uname)
            _apply_csrf(client, h)
            res = await client.get(url, headers=h)
            print(f"raw HTTP {res.status_code}: {res.text[:400]}")

        print("\n--- feed page 1 (user_id path) ---")
        feed1b = await _feed_user_page(client, username=uname, user_id=uid, max_id=None, count=12, mobile=False)
        if feed1b:
            nodes, cursor, more = _nodes_from_feed(feed1b)
            print(f"items={len(nodes)} next_max_id={feed1b.get('next_max_id')!r} more_available={feed1b.get('more_available')!r}")
        else:
            url = f"https://www.instagram.com/api/v1/feed/user/{uid}/?count=12"
            h = _client_headers(uname)
            _apply_csrf(client, h)
            res = await client.get(url, headers=h)
            print(f"FAILED user_id feed: HTTP {res.status_code}: {res.text[:400]}")

        # Determine cursor for page 2
        seed_nodes = []
        if feed1:
            seed_nodes, cursor, _ = _nodes_from_feed(feed1)
        elif edges:
            seed_nodes = [e.get("node") for e in edges if isinstance(e.get("node"), dict)]
            cursor = _cursor_from_node(seed_nodes[-1]) if seed_nodes else None

        max_id = None
        if feed1 and feed1.get("next_max_id"):
            max_id = str(feed1["next_max_id"])
        elif seed_nodes:
            max_id = _cursor_from_node(seed_nodes[-1])

        print(f"\n--- feed page 2 with max_id={max_id!r} ---")
        if max_id:
            feed2 = await _feed_user_page_username(client, username=uname, max_id=max_id, count=12)
            if feed2:
                nodes2, cursor2, more2 = _nodes_from_feed(feed2)
                print(f"items={len(nodes2)} next_max_id={feed2.get('next_max_id')!r} more_available={feed2.get('more_available')!r}")
                codes1 = {str(n.get('code') or n.get('shortcode')) for n in seed_nodes}
                codes2 = {str(n.get('code') or n.get('shortcode')) for n in nodes2}
                overlap = codes1 & codes2
                print(f"overlap_with_page1={len(overlap)} new={len(codes2 - codes1)}")
                if nodes2:
                    print(f"page2 first={nodes2[0].get('code')} last={nodes2[-1].get('code')}")
            else:
                url = f"https://www.instagram.com/api/v1/feed/user/{uname}/username/?count=12&max_id={max_id}"
                h = _client_headers(uname)
                _apply_csrf(client, h)
                res = await client.get(url, headers=h)
                print(f"FAILED page2 username: HTTP {res.status_code}: {res.text[:500]}")

            feed2b = await _feed_user_page(client, username=uname, user_id=uid, max_id=max_id, count=12, mobile=False)
            if feed2b:
                nodes2b, _, _ = _nodes_from_feed(feed2b)
                print(f"user_id page2 items={len(nodes2b)} next_max_id={feed2b.get('next_max_id')!r}")
            else:
                url = f"https://www.instagram.com/api/v1/feed/user/{uid}/?count=12&max_id={max_id}"
                h = _client_headers(uname)
                _apply_csrf(client, h)
                res = await client.get(url, headers=h)
                print(f"FAILED page2 user_id: HTTP {res.status_code}: {res.text[:500]}")

            print("\n--- mobile feed page 2 ---")
            feed2m = await _feed_user_page(client, username=uname, user_id=uid, max_id=max_id, count=12, mobile=True)
            if feed2m:
                nodes2m, _, _ = _nodes_from_feed(feed2m)
                print(f"mobile items={len(nodes2m)} next_max_id={feed2m.get('next_max_id')!r} more={feed2m.get('more_available')!r}")
            else:
                url = f"https://i.instagram.com/api/v1/feed/user/{uid}/?count=12&max_id={max_id}"
                h = _client_headers(uname)
                h["User-Agent"] = (
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Instagram 312.0.0.0.0"
                )
                _apply_csrf(client, h)
                res = await client.get(url, headers=h)
                print(f"FAILED mobile page2: HTTP {res.status_code}: {res.text[:500]}")
        else:
            print("No max_id available to test page 2")

        # GraphQL with end_cursor
        if end_cursor:
            print(f"\n--- GraphQL page with after=end_cursor ---")
            from urllib.parse import quote

            variables = json.dumps({"id": uid, "first": 12, "after": end_cursor}, separators=(",", ":"))
            for qh in (
                "e769aa130647d2354c40ea6a439bfc08",
                "69cba40317214287afd42f5a24efd3f5",
            ):
                url = f"https://www.instagram.com/graphql/query/?query_hash={qh}&variables={quote(variables)}"
                h = _client_headers(uname)
                _apply_csrf(client, h)
                res = await client.get(url, headers=h)
                print(f"query_hash={qh} HTTP {res.status_code} body={res.text[:200]}")

            for doc_id in ("7950326061742207", "7898261790222653"):
                h = _client_headers(uname)
                h["Content-Type"] = "application/x-www-form-urlencoded"
                _apply_csrf(client, h)
                data = {
                    "variables": json.dumps({"id": uid, "first": 12, "after": end_cursor}, separators=(",", ":")),
                    "doc_id": doc_id,
                    "server_timestamps": "true",
                }
                res = await client.post("https://www.instagram.com/graphql/query", headers=h, data=data)
                print(f"doc_id={doc_id} HTTP {res.status_code} body={res.text[:250]}")


async def diagnose_browser_scroll(username: str) -> None:
    """Watch network + DOM while scrolling a profile in Playwright."""
    from playwright.async_api import async_playwright

    uname = username.lstrip("@").strip().lower()
    print(f"\n======== BROWSER SCROLL @{uname} ========")

    graphql_hits = []
    feed_hits = []
    other_api = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1365, "height": 900},
            locale="en-US",
        )
        await context.set_extra_http_headers(
            {"Accept-Language": "en-US,en;q=0.9", "X-IG-App-ID": "936619743392459"}
        )
        page = await context.new_page()

        def on_request(req):
            u = req.url
            if "graphql" in u:
                graphql_hits.append(u[:120])
            elif "/api/v1/feed/user/" in u:
                feed_hits.append(u[:160])
            elif "/api/v1/" in u:
                other_api.append(u[:120])

        async def on_response(resp):
            u = resp.url
            if "/api/v1/feed/user/" in u or "graphql" in u or "web_profile" in u:
                try:
                    body = await resp.text()
                    print(f"RESP {resp.status} {u[:100]} len={len(body)} head={body[:120]!r}")
                except Exception as e:
                    print(f"RESP {resp.status} {u[:100]} read_err={e}")

        page.on("request", on_request)
        page.on("response", on_response)

        url = f"https://www.instagram.com/{uname}/"
        print(f"goto {url}")
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            print(f"goto status={resp.status if resp else None} title={await page.title()!r}")
        except Exception:
            traceback.print_exc()
            await browser.close()
            return

        await asyncio.sleep(3)

        async def count_posts():
            return await page.evaluate(
                """() => {
                  const anchors = Array.from(document.querySelectorAll('a[href*="/p/"], a[href*="/reel/"]'));
                  const seen = new Set();
                  for (const a of anchors) {
                    const m = (a.getAttribute('href')||'').match(/\\/(p|reel)\\/([^\\/]+)/);
                    if (m) seen.add(m[2]);
                  }
                  const h = Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);
                  return {posts: seen.size, height: h, nodes: document.querySelectorAll('*').length};
                }"""
            )

        prev = await count_posts()
        print(f"scroll0: {prev} feed_reqs={len(feed_hits)} gql={len(graphql_hits)}")

        for i in range(15):
            before_feed = len(feed_hits)
            before_gql = len(graphql_hits)
            before_h = prev["height"]
            before_posts = prev["posts"]
            before_nodes = prev["nodes"]

            await page.evaluate(
                """(step) => {
                  const h = Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);
                  window.scrollTo(0, Math.min(h, (step + 1) * (window.innerHeight * 0.9)));
                  if (step % 3 === 2) window.scrollTo(0, h);
                }""",
                i,
            )
            await asyncio.sleep(1.5)
            cur = await count_posts()
            print(
                f"scroll{i+1}: posts={cur['posts']} (+{cur['posts']-before_posts}) "
                f"height={cur['height']} (changed={cur['height']!=before_h}) "
                f"dom_nodes={cur['nodes']} (+{cur['nodes']-before_nodes}) "
                f"feed_reqs=+{len(feed_hits)-before_feed} gql=+{len(graphql_hits)-before_gql} "
                f"total_feed={len(feed_hits)} total_gql={len(graphql_hits)}"
            )
            prev = cur

            if (
                cur["posts"] == before_posts
                and cur["height"] == before_h
                and len(feed_hits) == before_feed
                and len(graphql_hits) == before_gql
                and cur["nodes"] == before_nodes
                and i >= 3
            ):
                print("STOP: no new posts AND no height AND no network AND no DOM")
                break

        # Try in-page feed pagination with browser cookies
        print("\n--- in-browser feed pagination ---")
        result = await page.evaluate(
            """async (username) => {
              const out = [];
              try {
                const r1 = await fetch(`/api/v1/users/web_profile_info/?username=${encodeURIComponent(username)}`, {
                  credentials: 'include',
                  headers: {'X-IG-App-ID':'936619743392459','X-Requested-With':'XMLHttpRequest'},
                });
                out.push({step:'web_profile', status:r1.status, ok:r1.ok});
                if (!r1.ok) return out;
                const j1 = await r1.json();
                const user = j1.data && j1.data.user;
                const uid = user && (user.id || user.pk);
                const edges = (user && user.edge_owner_to_timeline_media && user.edge_owner_to_timeline_media.edges) || [];
                const count = user && user.edge_owner_to_timeline_media && user.edge_owner_to_timeline_media.count;
                out.push({step:'profile', uid, count, edges: edges.length});
                const last = edges[edges.length-1] && edges[edges.length-1].node;
                const maxId = last && (last.id || last.pk);
                const q = new URLSearchParams({count:'12'});
                if (maxId) q.set('max_id', String(maxId).split('_')[0]);
                for (const path of [
                  `/api/v1/feed/user/${encodeURIComponent(username)}/username/?${q}`,
                  `/api/v1/feed/user/${uid}/?${q}`,
                ]) {
                  try {
                    const r = await fetch(path, {
                      credentials:'include',
                      headers:{'X-IG-App-ID':'936619743392459','X-ASBD-ID':'129477','X-Requested-With':'XMLHttpRequest'},
                    });
                    const text = await r.text();
                    let items = 0, more=null, next=null;
                    try {
                      const j = JSON.parse(text);
                      items = (j.items||[]).length;
                      more = j.more_available;
                      next = j.next_max_id;
                    } catch(e) {}
                    out.push({step:'feed', path: path.slice(0,80), status:r.status, items, more, next: String(next).slice(0,40), head: text.slice(0,120)});
                  } catch(e) {
                    out.push({step:'feed_err', path: path.slice(0,80), error: String(e)});
                  }
                }
              } catch(e) {
                out.push({step:'fatal', error: String(e)});
              }
              return out;
            }""",
            uname,
        )
        print(json.dumps(result, indent=2))

        await browser.close()


async def main() -> None:
    names = [a for a in sys.argv[1:] if not a.startswith("-")]
    do_browser = "--browser" in sys.argv or not names
    if not names:
        names = ["instagram"]  # known public account with many posts
    for name in names:
        try:
            await diagnose(name)
        except Exception:
            traceback.print_exc()
        if do_browser or "--browser" in sys.argv:
            try:
                await diagnose_browser_scroll(name)
            except Exception:
                traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
