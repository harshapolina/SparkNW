"""Resource-blocking and feed-cursor stop rules (no network)."""

from instascope_scraper.http_profile import decide_feed_cursor
from instascope_scraper.network_policy import should_block_request


def test_block_static_cdn_js_and_css():
    assert should_block_request(
        "https://static.cdninstagram.com/rsrc.php/v3/foo.js", "script"
    )
    assert should_block_request(
        "https://static.cdninstagram.com/rsrc.php/v3/foo.css", "stylesheet"
    )


def test_block_media_and_scontent():
    assert should_block_request(
        "https://scontent.cdninstagram.com/v/t51.2885-15/x.jpg", "image"
    )
    assert should_block_request(
        "https://www.instagram.com/static/images/ico.png", "image"
    )
    assert should_block_request("https://example.com/font.woff2", "font")


def test_allow_instagram_html_and_feed_json():
    assert not should_block_request("https://www.instagram.com/niat.genai/", "document")
    assert not should_block_request(
        "https://www.instagram.com/api/v1/feed/user/abc/username/?count=12",
        "xhr",
    )
    assert not should_block_request(
        "https://www.instagram.com/api/v1/users/web_profile_info/?username=x",
        "fetch",
    )
    assert not should_block_request(
        "https://i.instagram.com/api/v1/feed/user/123/?count=12",
        "xhr",
    )


def test_decide_feed_cursor_stops_repeats():
    requested = {"111"}
    _, action = decide_feed_cursor(max_id="111", next_cursor="111", added=0, requested=requested)
    assert action == "stop_stuck"
    _, action = decide_feed_cursor(max_id="111", next_cursor="222", added=0, requested={"111", "222"})
    assert action == "stop_repeat"
    nxt, action = decide_feed_cursor(max_id="111", next_cursor="222", added=5, requested={"111"})
    assert action == "advance"
    assert nxt == "222"
