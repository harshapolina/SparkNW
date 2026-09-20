"""Logged-out Polaris timeline parsing (no network).

Fixtures below mirror the real payload shapes captured from instagram.com in
Sep 2026: the profile HTML carries a Relay preload blob, and the embed document
carries engagement counts either escaped or plain depending on the route.
"""

from datetime import timezone

from instascope_scraper.polaris import (
    PolarisUnavailable,
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
