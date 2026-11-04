"""Campus × month upload counting (no DB)."""

from datetime import datetime
from types import SimpleNamespace

from instascope_shared.services.spark import (
    _normalize_campus,
    build_campus_uploads,
    month_keys_inclusive,
)

NOIDA = "Noida International University (Noida)"
CDU = "CDU (Hyderabad)"
NIAT_KKH = "NIAT - KKH (Hyderabad)"
AURORA = "Aurora Deemed University (Hyderabad)"
VGU = "Vivekananda Global University (Jaipur)"
NRI = "NRI (Vijayawada)"
AMET = "AMET University (Chennai)"
CHALAPATHI = "Chalapathi Institute of Technology (Guntur)"


def test_month_keys_inclusive_spans_jul_aug():
    keys = month_keys_inclusive(datetime(2026, 7, 15), datetime(2026, 8, 18))
    assert keys == ["2026-07", "2026-08"]


def test_campus_uploads_counts_all_ig_posts_and_yt_uploads():
    campus_by_pid = {"a": CDU, "b": NOIDA}
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
    assert ig[CDU]["counts"] == [1, 2]
    assert ig[NOIDA]["counts"] == [0, 1]
    assert yt[CDU]["counts"] == [0, 1]
    assert yt[NOIDA]["counts"] == [1, 0]
    assert ov[CDU]["total"] == 4
    assert ov[NOIDA]["total"] == 2
    assert out["overall"]["grand_total"] == 6
    assert out["instagram"]["grand_total"] == 4
    assert out["youtube"]["grand_total"] == 2


def test_campus_uploads_hides_unassigned_orphan_bucket():
    """Uploads with no matching profile must not appear as a campus row."""
    campus_by_pid = {"a": CDU}
    posts = [
        SimpleNamespace(profile_id="a", posted_at=datetime(2026, 7, 20)),
        SimpleNamespace(profile_id="missing", posted_at=datetime(2026, 7, 21)),
        SimpleNamespace(profile_id="missing", posted_at=datetime(2026, 8, 1)),
    ]
    out = build_campus_uploads(
        campus_by_pid=campus_by_pid,
        posts=posts,
        videos=[],
        start=datetime(2026, 7, 15),
        end=datetime(2026, 8, 18),
    )
    campuses = [r["campus"] for r in out["overall"]["rows"]]
    assert campuses == [CDU]
    assert "—" not in campuses
    assert out["overall"]["grand_total"] == 1
    assert out["overall"]["totals"] == [1, 0]


def test_normalize_campus_folds_dual_college_aliases():
    assert _normalize_campus("KKH") == NIAT_KKH
    assert _normalize_campus("CDU, HYD") == CDU
    assert _normalize_campus("CDU") == CDU
    assert _normalize_campus("NIAT, Aurora") == AURORA
    assert _normalize_campus("NIAT, VGU Campus") == VGU
    assert _normalize_campus("NIAT, VIVEKANANDA") == VGU
    assert _normalize_campus("NIAT X NRI") == NRI
    assert _normalize_campus("NIAT , CHALAPATHI") == CHALAPATHI
    assert _normalize_campus("NIAT, AMET University") == AMET
    assert _normalize_campus("AMET University ( Chennai)") == AMET
    assert _normalize_campus("Noida intemational University (Noida)") == NOIDA


def test_campus_uploads_merges_alias_rows_into_screenshot_campuses():
    """Dual-college roster labels must roll into the cleaned campus-wise board."""
    campus_by_pid = {
        "kkh": "KKH",
        "cdu_alias": "CDU, HYD",
        "aurora": "NIAT, Aurora",
        "nri": "NIAT X NRI",
        "orphan": "Random Unknown College",
    }
    posts = [
        SimpleNamespace(profile_id="kkh", posted_at=datetime(2026, 7, 20)),
        SimpleNamespace(profile_id="kkh", posted_at=datetime(2026, 8, 1)),
        SimpleNamespace(profile_id="cdu_alias", posted_at=datetime(2026, 7, 21)),
        SimpleNamespace(profile_id="aurora", posted_at=datetime(2026, 8, 2)),
        SimpleNamespace(profile_id="nri", posted_at=datetime(2026, 8, 3)),
        SimpleNamespace(profile_id="orphan", posted_at=datetime(2026, 8, 4)),
    ]
    out = build_campus_uploads(
        campus_by_pid=campus_by_pid,
        posts=posts,
        videos=[],
        start=datetime(2026, 7, 15),
        end=datetime(2026, 8, 18),
    )
    campuses = [r["campus"] for r in out["overall"]["rows"]]
    assert campuses == [NIAT_KKH, AURORA, CDU, NRI]
    assert "KKH" not in campuses
    assert "NIAT, Aurora" not in campuses
    assert "Random Unknown College" not in campuses
    by = {r["campus"]: r for r in out["overall"]["rows"]}
    assert by[NIAT_KKH]["counts"] == [1, 1]
    assert by[CDU]["counts"] == [1, 0]
    assert by[AURORA]["counts"] == [0, 1]
    assert by[NRI]["counts"] == [0, 1]
    assert out["overall"]["grand_total"] == 5
