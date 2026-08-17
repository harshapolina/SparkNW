"""Unit tests for SPARK points calculator (no DB)."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from instascope_shared.services.spark_points import (
    compute_points_breakdown,
    growth_points_for_window,
    long_form_points,
    short_form_points,
)


def _post(*, media_type: str, views: int, posted_at: datetime, caption: str = "", shortcode: str = "x"):
    return SimpleNamespace(
        media_type=media_type,
        views=views,
        posted_at=posted_at,
        caption=caption,
        shortcode=shortcode,
        ig_post_id=shortcode,
        likes=0,
        comments=0,
    )


def _video(*, views: int, published_at: datetime, is_short: bool = False, duration_seconds: int | None = None, video_id: str = "v1"):
    return SimpleNamespace(
        view_count=views,
        published_at=published_at,
        is_short=is_short,
        duration_seconds=duration_seconds,
        video_id=video_id,
        like_count=0,
        comment_count=0,
    )


def test_short_and_long_bands():
    assert short_form_points(999) == 0
    assert short_form_points(1_000) == 5
    assert short_form_points(50_000) == 30
    assert short_form_points(100_000) == 60
    assert long_form_points(499) == 0
    assert long_form_points(500) == 10
    assert long_form_points(10_000) == 50


def test_growth_combined_and_50k_single():
    # Combined 800 → 12_000 unlocks 1k+5k+10k = 250
    assert growth_points_for_window(end_ig=10_000, end_yt=2_000, start_ig=500, start_yt=300) == 250
    # 50k on IG alone
    assert growth_points_for_window(end_ig=50_000, end_yt=0, start_ig=40_000, start_yt=0) == 1000
    # Already had 50k at start → no new 50k pts; still mid milestones if crossed
    assert growth_points_for_window(end_ig=55_000, end_yt=0, start_ig=50_000, start_yt=0) == 0


def test_weekly_consistency_accumulates():
    # Two separate ISO weeks each with 2 shorts + 1 carousel → 20 pts
    w1 = [
        _post(media_type="reel", views=100, posted_at=datetime(2026, 7, 20), shortcode="a"),
        _post(media_type="reel", views=100, posted_at=datetime(2026, 7, 21), shortcode="b"),
        _post(media_type="carousel", views=100, posted_at=datetime(2026, 7, 22), shortcode="c"),
    ]
    w2 = [
        _post(media_type="reel", views=100, posted_at=datetime(2026, 7, 27), shortcode="d"),
        _post(media_type="reel", views=100, posted_at=datetime(2026, 7, 28), shortcode="e"),
        _post(media_type="carousel", views=100, posted_at=datetime(2026, 7, 29), shortcode="f"),
    ]
    scored = compute_points_breakdown(
        posts=w1 + w2,
        followers=0,
        as_of=datetime(2026, 8, 1),
        from_date=datetime(2026, 7, 15),
        include_youtube=False,
    )
    assert scored["consistency"] == 20


def test_crosspost_counts_once_for_performance():
    day = datetime(2026, 7, 20, 12, 0, 0)
    posts = [_post(media_type="reel", views=12_000, posted_at=day, shortcode="ig1")]
    videos = [_video(views=80_000, published_at=day, is_short=True, duration_seconds=45, video_id="yt1")]
    scored = compute_points_breakdown(
        posts=posts,
        videos=videos,
        followers=0,
        as_of=datetime(2026, 8, 1),
        from_date=datetime(2026, 7, 15),
        include_youtube=True,
    )
    # max(12k, 80k) → 30 pts short band once, not 15+30
    assert scored["performance"] == 30


def test_manual_categories_capped():
    scored = compute_points_breakdown(
        posts=[],
        followers=0,
        as_of=datetime(2026, 8, 1),
        from_date=datetime(2026, 7, 15),
        insights={
            "spark_points": {"collaborations": 9999, "monthly_bonuses": 100},
            "spark_bonus_points": 50,
        },
        include_youtube=False,
    )
    assert scored["collaborations"] == 850
    assert scored["monthly_bonuses"] == 100
    assert scored["bonus"] == 50
    assert scored["points"] == 850 + 100 + 50


def test_merge_spark_scoring_insights_keeps_admin_bonus():
    from instascope_shared.services.spark_points import merge_spark_scoring_insights

    merged = merge_spark_scoring_insights(
        {"spark_bonus_points": 80, "spark_bonus_log": [{"points": 80}], "sampled_posts": 12},
        {"sampled_posts": 4, "avg_likes": 10},
    )
    assert merged["sampled_posts"] == 4
    assert merged["avg_likes"] == 10
    assert merged["spark_bonus_points"] == 80
    assert merged["spark_bonus_log"] == [{"points": 80}]
