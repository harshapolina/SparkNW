"""Student access classification (no DB)."""

from types import SimpleNamespace

from instascope_shared.services.student_access import (
    classify_access,
    credentials_from_profile,
    _matches_access_filter,
)
from instascope_shared.schemas import StudentAccessRow


def test_classify_access_needs_both_credentials():
    assert classify_access("", "alice", None) == "incomplete"
    assert classify_access("N25H01A0349", "", True) == "incomplete"
    assert classify_access("N25H01A0349", "alice", None) == "has_access"
    assert classify_access("N25H01A0349", "alice", True) == "has_access"
    assert classify_access("N25H01A0349", "alice", False) == "blocked"


def test_credentials_from_profile_prefer_username_then_roster():
    p = SimpleNamespace(
        username="coolcreator",
        student={"student_id": " n25h01a0349 ", "instagram_username": "other"},
    )
    assert credentials_from_profile(p) == ("N25H01A0349", "coolcreator")

    p2 = SimpleNamespace(
        username="",
        student={"student_id": "N1", "instagram_url": "https://instagram.com/fromurl"},
    )
    assert credentials_from_profile(p2) == ("N1", "fromurl")


def test_access_filter_groups_incomplete_and_blocked_as_no_access():
    granted = StudentAccessRow(
        profile_id="1",
        full_name="A",
        student_id="N1",
        instagram_username="a",
        access="has_access",
        has_account=True,
        is_active=True,
    )
    ready = StudentAccessRow(
        profile_id="2",
        full_name="B",
        student_id="N2",
        instagram_username="b",
        access="has_access",
        has_account=False,
        is_active=None,
    )
    missing = StudentAccessRow(
        profile_id="3",
        full_name="C",
        student_id="",
        instagram_username="c",
        access="incomplete",
        has_account=False,
    )
    blocked = StudentAccessRow(
        profile_id="4",
        full_name="D",
        student_id="N4",
        instagram_username="d",
        access="blocked",
        has_account=True,
        is_active=False,
    )
    assert _matches_access_filter(granted, "has_access")
    assert _matches_access_filter(ready, "has_access")
    assert _matches_access_filter(ready, "never_signed_in")
    assert not _matches_access_filter(granted, "never_signed_in")
    assert _matches_access_filter(missing, "no_access")
    assert _matches_access_filter(blocked, "no_access")
    assert not _matches_access_filter(granted, "no_access")
