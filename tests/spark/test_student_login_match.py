"""Student login matching (no DB)."""

from types import SimpleNamespace

from instascope_shared.services.auth import _norm_ig_username, _norm_student_id, _profile_matches_login


def _profile(**kwargs):
    student = kwargs.pop("student", {})
    return SimpleNamespace(username=kwargs.get("username", ""), student=student)


def test_norm_student_id_strips_spaces_and_uppercases():
    assert _norm_student_id(" n25h01a0349 ") == "N25H01A0349"


def test_norm_ig_username_from_url_and_handle():
    assert _norm_ig_username("@CoolCreator") == "coolcreator"
    assert _norm_ig_username("https://instagram.com/coolcreator/") == "coolcreator"


def test_profile_matches_login_by_roster_fields():
    p = _profile(
        username="other",
        student={
            "student_id": "N25H01A0349",
            "instagram_url": "https://www.instagram.com/coolcreator",
        },
    )
    assert _profile_matches_login(p, "N25H01A0349", "coolcreator")
    assert not _profile_matches_login(p, "N25H01A0349", "someoneelse")
    assert not _profile_matches_login(p, "WRONGID", "coolcreator")
