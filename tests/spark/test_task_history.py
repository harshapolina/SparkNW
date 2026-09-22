"""Task history timeline: complete, dated, linked, and summing to the total (no DB)."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

from instascope_shared.services.spark_points import (
    PERFORMANCE_CAP,
    bonus_ledger_lines,
    compute_points_breakdown,
)

AS_OF = datetime(2026, 9, 22, 12, 0)


def _reel(day: datetime, views: int, code: str):
    return SimpleNamespace(
        media_type="reel",
        views=views,
        posted_at=day,
        caption="",
        shortcode=code,
        ig_post_id=code,
        permalink=f"https://www.instagram.com/p/{code}/",
        likes=0,
        comments=0,
    )


def _ledger(*entries):
    """Ledger rows as stored: newest first."""
    return {"spark_bonus_log": list(entries)}


def test_bonus_ledger_itemises_each_award_with_reason_and_date():
    insights = _ledger(
        {"points": 25, "reason": "Challenge 04 (Sept)", "added_at": "2026-09-18T10:00:00", "added_by": "admin@x"},
        {"points": 250, "reason": "Challenge 01", "added_at": "2026-08-31T09:00:00", "added_by": "admin@x"},
    )
    lines = bonus_ledger_lines(insights, total=275, profile_id="p1", as_of=AS_OF)
    assert [(ln["title"], ln["points"], ln["date"]) for ln in lines] == [
        ("Challenge 01", 250, "2026-08-31"),
        ("Challenge 04 (Sept)", 25, "2026-09-18"),
    ]
    assert sum(ln["points"] for ln in lines) == 275


def test_bonus_ledger_never_exposes_who_added_it():
    insights = _ledger({"points": 10, "reason": "x", "added_at": "2026-09-01", "added_by": "admin@x"})
    for ln in bonus_ledger_lines(insights, total=10, profile_id="p1", as_of=AS_OF):
        assert "added_by" not in ln
        assert "admin@x" not in str(ln)


def test_bonus_ledger_reconciles_floor_at_zero():
    # +50 then -80: the balance floors at 0, so the ledger sums to -30 but 0 counts.
    insights = _ledger(
        {"points": -80, "reason": "penalty", "added_at": "2026-09-02"},
        {"points": 50, "reason": "award", "added_at": "2026-09-01"},
    )
    lines = bonus_ledger_lines(insights, total=0, profile_id="p1", as_of=AS_OF)
    assert sum(ln["points"] for ln in lines) == 0
    assert any(ln["id"].endswith("-balance") for ln in lines)


def test_bonus_ledger_covers_points_awarded_before_the_ledger():
    lines = bonus_ledger_lines({}, total=40, profile_id="p1", as_of=AS_OF)
    assert [ln["points"] for ln in lines] == [40]


def test_bonus_ledger_ids_stay_stable_as_awards_are_added():
    old = _ledger({"points": 5, "added_at": "2026-09-01"})
    new = _ledger({"points": 7, "added_at": "2026-09-10"}, {"points": 5, "added_at": "2026-09-01"})
    first = {ln["points"]: ln["id"] for ln in bonus_ledger_lines(old, total=5, profile_id="p", as_of=AS_OF)}
    second = {ln["points"]: ln["id"] for ln in bonus_ledger_lines(new, total=12, profile_id="p", as_of=AS_OF)}
    assert first[5] == second[5]


def test_consistency_awards_dated_by_the_week_that_earned_them():
    # Four reels in ISO week 36 (Mon 31 Aug .. Sun 6 Sep 2026) → weekly boost.
    monday = datetime(2026, 8, 31, 10, 0)
    posts = [_reel(monday + timedelta(days=i), 100, f"c{i}") for i in range(4)]
    out = compute_points_breakdown(posts=posts, followers=0, as_of=AS_OF, from_date=datetime(2026, 7, 15))
    cons = [t for t in out["task_history"] if t["category"] == "Consistency" and t["status"] == "approved"]
    assert cons and cons[0]["date"] == "2026-09-06"


def test_performance_lines_link_to_the_post():
    posts = [_reel(datetime(2026, 9, 1), 60_000, "ABC123")]
    out = compute_points_breakdown(posts=posts, followers=0, as_of=AS_OF, from_date=datetime(2026, 7, 15))
    perf = [t for t in out["task_history"] if t["category"] == "Performance"]
    assert perf[0]["shortcode"] == "ABC123"
    assert perf[0]["url"] == "https://www.instagram.com/p/ABC123/"


def test_capped_performance_still_sums_to_counted_points():
    # Many 100k+ reels blow through the performance cap.
    posts = [
        _reel(datetime(2026, 7, 20) + timedelta(days=i), 150_000, f"p{i}")
        for i in range(60)
    ]
    out = compute_points_breakdown(posts=posts, followers=0, as_of=AS_OF, from_date=datetime(2026, 7, 15))
    assert out["performance"] == PERFORMANCE_CAP
    assert out["performance_raw"] > PERFORMANCE_CAP
    perf_sum = sum(t["points"] for t in out["task_history"] if t["category"] == "Performance")
    assert perf_sum == PERFORMANCE_CAP
    assert any(t["status"] == "capped" for t in out["task_history"])


def test_consistency_lines_sum_to_counted_points():
    # Daily posts across the whole window → a weekly boost every week.
    start = datetime(2026, 7, 15, 9, 0)
    posts = [_reel(start + timedelta(days=i), 10, f"d{i}") for i in range((AS_OF - start).days)]
    out = compute_points_breakdown(posts=posts, followers=0, as_of=AS_OF, from_date=start)
    cons_sum = sum(t["points"] for t in out["task_history"] if t["category"] == "Consistency")
    assert cons_sum == out["consistency"] > 0


def test_consistency_cap_line_reconciles(monkeypatch):
    # The real cap (660) is out of reach inside one programme window, so lower it.
    import instascope_shared.services.spark_points as sp

    monkeypatch.setattr(sp, "CONSISTENCY_CAP", 30)
    start = datetime(2026, 7, 15, 9, 0)
    posts = [_reel(start + timedelta(days=i), 10, f"d{i}") for i in range((AS_OF - start).days)]
    out = sp.compute_points_breakdown(posts=posts, followers=0, as_of=AS_OF, from_date=start)
    assert out["consistency"] == 30
    cons = [t for t in out["task_history"] if t["category"] == "Consistency"]
    assert sum(t["points"] for t in cons) == 30
    assert any(t["status"] == "capped" for t in cons)
