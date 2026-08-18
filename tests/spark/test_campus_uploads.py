"""Campus × month upload counting (no DB)."""

from datetime import datetime
from types import SimpleNamespace

from instascope_shared.services.spark import build_campus_uploads, month_keys_inclusive


def test_month_keys_inclusive_spans_jul_aug():
    keys = month_keys_inclusive(datetime(2026, 7, 15), datetime(2026, 8, 18))
    assert keys == ["2026-07", "2026-08"]


def test_campus_uploads_counts_all_ig_posts_and_yt_uploads():
    campus_by_pid = {"a": "CDU (Hyderabad)", "b": "Noida"}
    posts = [
        SimpleNamespace(profile_id="a", posted_at=datetime(2026, 7, 20)),
        SimpleNamespace(profile_id="a", posted_at=datetime(2026, 8, 2)),
        SimpleNamespace(profile_id="a", posted_at=datetime(2026, 8, 3)),
        SimpleNamespace(profile_id="b", posted_at=datetime(2026, 8, 1)),
        SimpleNamespace(profile_id="a", posted_at=datetime(2026, 6, 1)),  # before window month still keyed Jun — ignored
    ]
    videos = [
        SimpleNamespace(profile_id="a", published_at=datetime(2026, 8, 10)),
        SimpleNamespace(profile_id="b", published_at=datetime(2026, 7, 16)),
    ]
    out = build_campus_uploads(
        campus_by_pid=campus_by_pid,
        posts=posts,
        videos=videos,
        start=datetime(2026, 7, 15),
        end=datetime(2026, 8, 18),
    )
    assert [m["id"] for m in out["months"]] == ["2026-07", "2026-08"]
    ig = {r["campus"]: r for r in out["instagram"]["rows"]}
    yt = {r["campus"]: r for r in out["youtube"]["rows"]}
    ov = {r["campus"]: r for r in out["overall"]["rows"]}
    assert ig["CDU (Hyderabad)"]["counts"] == [1, 2]
    assert ig["Noida"]["counts"] == [0, 1]
    assert yt["CDU (Hyderabad)"]["counts"] == [0, 1]
    assert yt["Noida"]["counts"] == [1, 0]
    assert ov["CDU (Hyderabad)"]["total"] == 4
    assert ov["Noida"]["total"] == 2
    assert out["overall"]["grand_total"] == 6
    assert out["instagram"]["grand_total"] == 4
    assert out["youtube"]["grand_total"] == 2
