"""Logged-out Polaris timeline parsing (no network).

Fixtures below mirror the real payload shapes captured from instagram.com in
Sep 2026: the profile HTML carries a Relay preload blob, and the embed document
carries engagement counts either escaped or plain depending on the route.
"""

from datetime import timezone

from instascope_scraper.polaris import (
    PolarisUnavailable,
    collect_timeline,
    extract_bootstrap,
    nodes_to_posts,
    parse_engagement,
    pk_to_datetime,
)

import pytest

# Trimmed to the fields the parser actually reads.
PROFILE_HTML = (
    '<script type="application/json" data-sjs>{"require":[["ScheduledServerJS","handle",null,'
    '[{"__bbox":{"require":[["RelayPrefetchedStreamCache","next",[],'
    '["adp_PolarisLoggedOutDesktopWWWProfilePostsTabContentQueryRelayPreloader_6aaff60",'
    '{"__bbox":{"complete":true,"result":{"data":{"xig_user_by_username":{"pk":"74770863655",'
    '"full_name":"Murali Krishna","is_private":false,'
    '"follower_count":8938,"following_count":5,'
    '"polaris_ordered_timeline_connection":{"edges":['
    '{"node":{"__typename":"XIGPolarisVideoMedia","pk":"3984285244001148342",'
    '"code":"DdLBlHchN22","caption":{"text":"hello world"},'
    '"display_uri":"https://scontent.example/a.jpg","media_type":"2",'
    '"product_type":"clips","accessibility_caption":"Video by X"}},'
    '{"node":{"__typename":"XIGPolarisImageMedia","pk":"3983826488373409445",'
    '"code":"DdJZRV-Sfal","caption":{"text":"second"},'
    '"display_uri":"https://scontent.example/b.jpg","media_type":"1",'
    '"product_type":"feed"}}'
    '],"page_info":{"end_cursor":"CURSOR_ONE","has_next_page":true}},"id":"17841474869666357"}}'
    '}}}]]}}]]}</script>'
    # Instagram names the query again in a preloader/queryID pair further down.
    '<script type="application/json" data-sjs>{"require":[["RelayPreloader","init",null,'
    '[{"actorID":"0","preloaderID":"adp_PolarisLoggedOutDesktopWWWProfileRootContentQueryRelayPreloader_aaa",'
    '"queryID":"27981003384861049"},'
    '{"actorID":"0","preloaderID":"adp_PolarisLoggedOutDesktopWWWProfilePostsTabContentQueryRelayPreloader_6aaff60",'
    '"queryID":"27553725110923321"}]]]}</script>'
    '<script>requireLazy(["LSD"],function(){});'
    '["LSD",[],{"token":"AdSY9ZeOeNuiJTv46fQTDUkwfEk"},247]</script>'
)


def test_pk_to_datetime_matches_instagram_creation_time():
    dt = pk_to_datetime("3984285244001148342")
    assert dt is not None
    assert dt.tzinfo == timezone.utc
    # Cross-checked against the post's own accessibility caption (rendered in PT).
    assert dt.strftime("%Y-%m-%d") == "2026-09-12"


@pytest.mark.parametrize("bad", ["", "abc", "0", None, -5, "99999999999999999999999"])
def test_pk_to_datetime_rejects_non_media_ids(bad):
    assert pk_to_datetime(bad) is None


def test_extract_bootstrap_reads_doc_id_lsd_card_and_cursor():
    boot = extract_bootstrap(PROFILE_HTML)
    assert boot["doc_id"] == "27553725110923321"
    assert boot["lsd"] == "AdSY9ZeOeNuiJTv46fQTDUkwfEk"
    assert boot["cursor"] == "CURSOR_ONE"
    assert boot["followers"] == 8938
    assert boot["following"] == 5
    assert boot["full_name"] == "Murali Krishna"
    assert boot["is_private"] is False
    assert boot["ig_user_id"] == "74770863655"
    assert len(boot["nodes"]) == 2


def test_extract_bootstrap_raises_when_payload_absent():
    with pytest.raises(PolarisUnavailable):
        extract_bootstrap("<html><body>login wall, no preload</body></html>")


def test_nodes_to_posts_maps_schema_and_derives_dates():
    posts = nodes_to_posts(extract_bootstrap(PROFILE_HTML)["nodes"], username="x")
    assert [p.shortcode for p in posts] == ["DdLBlHchN22", "DdJZRV-Sfal"]
    reel, image = posts
    assert reel.media_type == "reel" and reel.is_video is True
    assert image.media_type == "image" and image.is_video is False
    assert reel.caption == "hello world"
    assert reel.permalink == "https://www.instagram.com/p/DdLBlHchN22/"
    assert reel.ig_post_id == "3984285244001148342"
    assert reel.posted_at and reel.posted_at.startswith("2026-09-12")
    # Counts stay zero until the embed enrich step fills them.
    assert reel.likes == 0 and reel.views == 0


def test_nodes_to_posts_drops_posts_before_the_cohort_floor():
    nodes = extract_bootstrap(PROFILE_HTML)["nodes"]
    newest = pk_to_datetime(nodes[0]["pk"])
    assert newest is not None
    floor = newest.timestamp() + 1  # everything is older than this
    assert nodes_to_posts(nodes, username="x", cohort_floor_unix=floor) == []
    keep = nodes_to_posts(nodes, username="x", cohort_floor_unix=0)
    assert len(keep) == 2


def test_nodes_to_posts_dedupes_by_shortcode():
    node = {"pk": "3984285244001148342", "code": "DUP", "__typename": "XIGPolarisImageMedia"}
    assert len(nodes_to_posts([node, dict(node)], username="x")) == 1


def test_parse_engagement_escaped_embed():
    html = (
        r'stuff \"edge_liked_by\":{\"count\":5644} more '
        r'\"edge_media_to_comment\":{\"count\":11691} '
        r'\"video_view_count\":128870 tail'
    )
    assert parse_engagement(html) == {"likes": 5644, "comments": 11691, "views": 128870}


def test_parse_engagement_unescaped_embed():
    html = (
        '{"edge_media_to_comment":{"count":11691},"edge_liked_by":{"count":5644},'
        '"video_view_count":128870,"product_type":"clips"}'
    )
    assert parse_engagement(html) == {"likes": 5644, "comments": 11691, "views": 128870}


def test_parse_engagement_partial_and_empty():
    assert parse_engagement('"edge_liked_by":{"count":7}') == {"likes": 7}
    assert parse_engagement("no counts here") == {}


@pytest.mark.asyncio
async def test_collect_timeline_honours_max_posts(monkeypatch):
    """Bulk passes max_posts=48; the walker must stop and truncate to it."""
    import instascope_scraper.polaris as mod

    # Each page yields 12 synthetic nodes and always claims another page.
    counter = {"n": 0}

    class FakePage:
        async def content(self):
            return PROFILE_HTML

        async def evaluate(self, _js, _args):
            counter["n"] += 1
            base = 3984285244001148342 - counter["n"] * 10_000_000_000
            edges = [
                {
                    "node": {
                        "pk": str(base - i * 1_000_000),
                        "code": f"C{counter['n']:02d}{i:02d}",
                        "__typename": "XIGPolarisImageMedia",
                    }
                }
                for i in range(12)
            ]
            payload = {
                "data": {
                    "xig_user_by_username": {
                        "polaris_ordered_timeline_connection": {
                            "edges": edges,
                            "page_info": {
                                "end_cursor": f"CUR{counter['n']}",
                                "has_next_page": True,
                            },
                        }
                    }
                }
            }
            import json as _json

            return {"status": 200, "text": _json.dumps(payload)}

    boot = await mod.collect_timeline(
        FakePage(), "someone", max_posts=48, delay_seconds=0
    )
    assert len(boot["nodes"]) == 48
    assert boot["capped"] is True
    # 2 from the fixture's first page + 12/page, so it must not run away.
    assert counter["n"] <= 5


@pytest.mark.asyncio
async def test_collect_timeline_uncapped_when_max_posts_zero(monkeypatch):
    """max_posts=0 means no cap; exhaustion is what stops the walk."""
    import json as _json

    import instascope_scraper.polaris as mod

    calls = {"n": 0}

    class FakePage:
        async def content(self):
            return PROFILE_HTML

        async def evaluate(self, _js, _args):
            calls["n"] += 1
            has_next = calls["n"] < 2
            edges = [
                {
                    "node": {
                        "pk": str(3984285244001148342 - calls["n"] * 10_000_000_000 - i),
                        "code": f"Z{calls['n']}{i}",
                        "__typename": "XIGPolarisImageMedia",
                    }
                }
                for i in range(5)
            ]
            return {
                "status": 200,
                "text": _json.dumps(
                    {
                        "data": {
                            "xig_user_by_username": {
                                "polaris_ordered_timeline_connection": {
                                    "edges": edges,
                                    "page_info": {
                                        "end_cursor": "NEXT",
                                        "has_next_page": has_next,
                                    },
                                }
                            }
                        }
                    }
                ),
            }

    boot = await mod.collect_timeline(FakePage(), "someone", max_posts=0, delay_seconds=0)
    assert boot["capped"] is False
    assert boot["feed_exhausted"] is True
    assert len(boot["nodes"]) == 12  # 2 seeded + 10 paged


# --- end-of-timeline detection ------------------------------------------------
# Only Instagram's explicit has_next_page=false may mark a timeline complete.
# A new account whose whole history is inside the programme window never
# reaches the cohort floor, so this flag is what lets its full scrape save —
# which makes a false positive (a stall read as "complete") the thing to avoid.


def _page(nodes, *, has_next, cursor="NEXT"):
    import json as _json

    return {
        "status": 200,
        "text": _json.dumps(
            {
                "data": {
                    "xig_user_by_username": {
                        "polaris_ordered_timeline_connection": {
                            "edges": [{"node": n} for n in nodes],
                            "page_info": {"end_cursor": cursor if has_next else None, "has_next_page": has_next},
                        }
                    }
                }
            }
        ),
    }


def _nodes(prefix, n, base=3984285244001148342):
    return [{"pk": str(base - i * 1_000_000), "code": f"{prefix}{i:02d}"} for i in range(n)]


class _Pages:
    """Fake Playwright page: bootstrap HTML, then scripted /api/graphql responses."""

    def __init__(self, html, responses):
        self.html = html
        self.responses = list(responses)
        self.calls = 0

    async def content(self):
        return self.html

    async def evaluate(self, _js, _args):
        self.calls += 1
        return self.responses.pop(0)


def test_bootstrap_reads_has_next_from_page_info():
    assert extract_bootstrap(PROFILE_HTML)["has_next"] is True
    last = PROFILE_HTML.replace('"end_cursor":"CURSOR_ONE","has_next_page":true', '"end_cursor":null,"has_next_page":false')
    boot = extract_bootstrap(last)
    assert boot["has_next"] is False and boot["cursor"] is None


@pytest.mark.asyncio
async def test_timeline_complete_when_instagram_says_no_more_pages():
    page = _Pages(PROFILE_HTML, [_page(_nodes("A", 12), has_next=True), _page(_nodes("B", 5), has_next=False)])
    boot = await collect_timeline(page, "x", delay_seconds=0)
    assert boot["timeline_complete"] is True
    assert len(boot["nodes"]) == 2 + 12 + 5


@pytest.mark.asyncio
async def test_single_page_account_is_complete_without_any_request():
    last = PROFILE_HTML.replace('"end_cursor":"CURSOR_ONE","has_next_page":true', '"end_cursor":null,"has_next_page":false')
    page = _Pages(last, [])
    boot = await collect_timeline(page, "x", delay_seconds=0)
    assert boot["timeline_complete"] is True and page.calls == 0


@pytest.mark.asyncio
async def test_stalled_walk_is_never_complete():
    page = _Pages(PROFILE_HTML, [_page(_nodes("A", 12), has_next=True), {"status": 429, "text": ""}])
    boot = await collect_timeline(page, "x", delay_seconds=0)
    assert boot["timeline_complete"] is False


@pytest.mark.asyncio
async def test_empty_page_is_not_proof_of_the_end():
    page = _Pages(PROFILE_HTML, [_page([], has_next=True)])
    boot = await collect_timeline(page, "x", delay_seconds=0)
    assert boot["timeline_complete"] is False


@pytest.mark.asyncio
async def test_capped_walk_is_not_complete_even_at_the_end():
    page = _Pages(PROFILE_HTML, [_page(_nodes("A", 12), has_next=False)])
    boot = await collect_timeline(page, "x", max_posts=5, delay_seconds=0)
    assert boot["capped"] is True and boot["timeline_complete"] is False


def test_unknown_payload_shape_leaves_the_end_unconfirmed():
    # Nodes recoverable by regex, but no parseable connection/page_info.
    html = (
        '"adp_PolarisLoggedOutDesktopWWWProfilePostsTabContentQueryRelayPreloader_x","queryID":"123"'
        '["LSD",[],{"token":"T"},1] "pk":"3984285244001148342","code":"ZZZZZ1"'
    )
    boot = extract_bootstrap(html)
    assert boot["nodes"] and boot["has_next"] is None and boot["cursor"] is None
