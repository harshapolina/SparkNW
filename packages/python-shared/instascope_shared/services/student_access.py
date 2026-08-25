"""Admin roster credentials: admission number + Instagram handle (student login)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import HTTPException, status

from instascope_shared.domain.instagram import extract_username, profile_url_for
from instascope_shared.models import DEFAULT_ORG_ID, Profile, ProfileStatus, User, UserRole
from instascope_shared.schemas import (
    StudentAccessCreateRequest,
    StudentAccessListResponse,
    StudentAccessRow,
    StudentAccessUpdateRequest,
)
from instascope_shared.services.auth import (
    _exact_ci,
    _norm_ig_username,
    _norm_student_id,
    ensure_student_user,
    org_profile_clause,
    profile_display_name,
)


def credentials_from_profile(profile) -> tuple[str, str]:
    student = getattr(profile, "student", None) or {}
    sid = _norm_student_id(str(student.get("student_id") or ""))
    ig = (
        _norm_ig_username(getattr(profile, "username", None) or "")
        or _norm_ig_username(str(student.get("instagram_username") or ""))
        or _norm_ig_username(str(student.get("instagram_handle") or ""))
        or _norm_ig_username(str(student.get("instagram_url") or ""))
    )
    return sid, ig


def classify_access(student_id: str, instagram_username: str, user_active: Optional[bool]) -> str:
    if not student_id or not instagram_username:
        return "incomplete"
    if user_active is False:
        return "blocked"
    return "has_access"


def _campus(profile) -> str:
    student = getattr(profile, "student", None) or {}
    return str(student.get("university") or "").strip()


def _to_row(profile: Profile, user: Optional[User]) -> StudentAccessRow:
    sid, ig = credentials_from_profile(profile)
    active = None if user is None else bool(user.is_active)
    return StudentAccessRow(
        profile_id=str(profile.id),
        full_name=profile_display_name(profile),
        student_id=sid,
        instagram_username=ig,
        campus=_campus(profile),
        access=classify_access(sid, ig, active),
        has_account=user is not None,
        is_active=active,
    )


def _matches_access_filter(row: StudentAccessRow, access_filter: str) -> bool:
    key = (access_filter or "all").strip().lower()
    if key in {"", "all"}:
        return True
    if key == "has_access":
        return row.access == "has_access"
    if key == "no_access":
        return row.access in {"incomplete", "blocked"}
    if key == "incomplete":
        return row.access == "incomplete"
    if key == "blocked":
        return row.access == "blocked"
    if key in {"signed_in", "account"}:
        return bool(row.has_account) and row.access == "has_access"
    if key in {"never_signed_in", "ready"}:
        return (not row.has_account) and row.access == "has_access"
    return True


def _parse_instagram(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Instagram username is required")
    try:
        return extract_username(text)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


async def _get_org_profile(org_id: str, profile_id: str) -> Profile:
    try:
        profile = await Profile.get(profile_id)
    except Exception as exc:
        name = exc.__class__.__name__
        if name in {"InvalidId", "ValidationError"}:
            profile = None
        else:
            raise
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    profile_org = getattr(profile, "org_id", None) or DEFAULT_ORG_ID
    if profile_org != org_id and getattr(profile, "org_id", None) not in {None, ""}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    return profile


async def _assert_student_id_free(org_id: str, student_id: str, *, exclude_id: Optional[str] = None) -> None:
    sid_rx = _exact_ci(student_id)
    found = await Profile.find(
        {"$and": [org_profile_clause(org_id), {"student.student_id": sid_rx}]}
    ).to_list()
    for other in found:
        if exclude_id and str(other.id) == str(exclude_id):
            continue
        other_sid, _ = credentials_from_profile(other)
        if other_sid == student_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Admission number {student_id} is already used by another student",
            )


async def _assert_instagram_free(org_id: str, username: str, *, exclude_id: Optional[str] = None) -> None:
    ig_rx = _exact_ci(username)
    found = await Profile.find(
        {
            "$and": [
                org_profile_clause(org_id),
                {
                    "$or": [
                        {"username": ig_rx},
                        {"student.instagram_username": ig_rx},
                    ]
                },
            ]
        }
    ).to_list()
    for other in found:
        if exclude_id and str(other.id) == str(exclude_id):
            continue
        _, other_ig = credentials_from_profile(other)
        if other_ig == username:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"@{username} is already used by another student",
            )


def _apply_student_fields(
    profile: Profile,
    *,
    student_id: Optional[str] = None,
    instagram_username: Optional[str] = None,
    full_name: Optional[str] = None,
    university: Optional[str] = None,
) -> None:
    student = dict(getattr(profile, "student", None) or {})
    if student_id is not None:
        student["student_id"] = student_id
    if instagram_username is not None:
        profile.username = instagram_username
        profile.profile_url = profile_url_for(instagram_username)
        student["instagram_username"] = instagram_username
        student["instagram_handle"] = f"@{instagram_username}"
        student["instagram_url"] = profile.profile_url
        if profile.status == ProfileStatus.UNAVAILABLE:
            profile.status = ProfileStatus.ACTIVE
        profile.last_error = None
    if full_name is not None:
        name = full_name.strip()
        if name:
            student["full_name"] = name
            profile.full_name = name
    if university is not None:
        campus = university.strip()
        if campus:
            student["university"] = campus
    profile.student = student
    if not getattr(profile, "org_id", None):
        profile.org_id = DEFAULT_ORG_ID
    profile.updated_at = datetime.utcnow()


async def _sync_linked_user(profile: Profile) -> Optional[User]:
    sid, _ = credentials_from_profile(profile)
    user = await User.find_one(User.profile_id == str(profile.id), User.role == UserRole.STUDENT)
    if not user and sid:
        user = await User.find_one(User.student_id == sid, User.role == UserRole.STUDENT)
    if not user:
        return None
    user.profile_id = str(profile.id)
    if sid:
        user.student_id = sid
    user.name = profile_display_name(profile)
    user.org_id = getattr(profile, "org_id", None) or DEFAULT_ORG_ID
    user.updated_at = datetime.utcnow()
    await user.save()
    return user


async def _users_for_profiles(profiles: list[Profile]) -> dict[str, User]:
    if not profiles:
        return {}
    pids = [str(p.id) for p in profiles]
    sids = [credentials_from_profile(p)[0] for p in profiles]
    sids = [s for s in sids if s]
    clause: dict = {"role": UserRole.STUDENT.value, "$or": [{"profile_id": {"$in": pids}}]}
    if sids:
        clause["$or"].append({"student_id": {"$in": sids}})
    users = await User.find(clause).to_list()
    by_pid: dict[str, User] = {}
    by_sid: dict[str, User] = {}
    for user in users:
        if getattr(user, "profile_id", None):
            by_pid[str(user.profile_id)] = user
        if getattr(user, "student_id", None):
            by_sid[_norm_student_id(user.student_id)] = user
    out: dict[str, User] = {}
    for profile in profiles:
        pid = str(profile.id)
        sid, _ = credentials_from_profile(profile)
        user = by_pid.get(pid) or (by_sid.get(sid) if sid else None)
        if user:
            out[pid] = user
    return out


async def list_student_access(
    org_id: str,
    *,
    q: Optional[str] = None,
    access: str = "all",
    page: int = 1,
    page_size: int = 50,
) -> StudentAccessListResponse:
    filt: dict = {"$and": [org_profile_clause(org_id)]}
    q_raw = (q or "").strip()
    if q_raw:
        rx = {"$regex": q_raw, "$options": "i"}
        filt["$and"].append(
            {
                "$or": [
                    {"username": rx},
                    {"full_name": rx},
                    {"student.full_name": rx},
                    {"student.student_id": rx},
                    {"student.instagram_username": rx},
                    {"student.instagram_handle": rx},
                    {"student.university": rx},
                ]
            }
        )

    profiles = await Profile.find(filt).sort([("student.full_name", 1), ("username", 1)]).to_list()
    users = await _users_for_profiles(profiles)
    rows = [_to_row(p, users.get(str(p.id))) for p in profiles]

    counts = {
        "all": len(rows),
        "has_access": sum(1 for r in rows if r.access == "has_access"),
        "no_access": sum(1 for r in rows if r.access in {"incomplete", "blocked"}),
        "incomplete": sum(1 for r in rows if r.access == "incomplete"),
        "blocked": sum(1 for r in rows if r.access == "blocked"),
    }
    filtered = [r for r in rows if _matches_access_filter(r, access)]
    page = max(int(page or 1), 1)
    page_size = min(max(int(page_size or 50), 1), 200)
    start = (page - 1) * page_size
    return StudentAccessListResponse(
        items=filtered[start : start + page_size],
        total=len(filtered),
        page=page,
        page_size=page_size,
        counts=counts,
    )


async def update_student_access(
    org_id: str,
    profile_id: str,
    payload: StudentAccessUpdateRequest,
) -> StudentAccessRow:
    profile = await _get_org_profile(org_id, profile_id)
    sid, ig = credentials_from_profile(profile)

    next_sid = sid
    next_ig = ig
    if payload.student_id is not None:
        next_sid = _norm_student_id(payload.student_id)
        if not next_sid:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Admission number is required")
        if next_sid != sid:
            await _assert_student_id_free(org_id, next_sid, exclude_id=str(profile.id))
    if payload.instagram_username is not None:
        next_ig = _parse_instagram(payload.instagram_username)
        if next_ig != ig:
            await _assert_instagram_free(org_id, next_ig, exclude_id=str(profile.id))

    _apply_student_fields(
        profile,
        student_id=next_sid if payload.student_id is not None else None,
        instagram_username=next_ig if payload.instagram_username is not None else None,
        full_name=payload.full_name,
        university=payload.university,
    )
    await profile.save()
    user = await _sync_linked_user(profile)

    if payload.access == "grant":
        user = await ensure_student_user(profile, is_active=True)
    elif payload.access == "revoke":
        user = await ensure_student_user(profile, is_active=False)

    return _to_row(profile, user)


async def create_student_access(org_id: str, owner_user_id: str, payload: StudentAccessCreateRequest) -> StudentAccessRow:
    sid = _norm_student_id(payload.student_id)
    ig = _parse_instagram(payload.instagram_username)
    if not sid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Admission number is required")

    sid_rx = _exact_ci(sid)
    ig_rx = _exact_ci(ig)
    candidates = await Profile.find(
        {
            "$and": [
                org_profile_clause(org_id),
                {
                    "$or": [
                        {"username": ig_rx},
                        {"student.instagram_username": ig_rx},
                        {"student.student_id": sid_rx},
                    ]
                },
            ]
        }
    ).to_list()
    matches: list[Profile] = []
    for profile in candidates:
        existing_sid, existing_ig = credentials_from_profile(profile)
        if existing_sid == sid or existing_ig == ig:
            matches.append(profile)
    distinct: dict[str, Profile] = {str(p.id): p for p in matches}
    if len(distinct) > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That admission number and Instagram handle belong to different students",
        )

    profile = next(iter(distinct.values()), None)
    if profile:
        await _assert_student_id_free(org_id, sid, exclude_id=str(profile.id))
        await _assert_instagram_free(org_id, ig, exclude_id=str(profile.id))
    else:
        await _assert_student_id_free(org_id, sid)
        await _assert_instagram_free(org_id, ig)
        profile = Profile(
            user_id=owner_user_id,
            org_id=org_id,
            username=ig,
            profile_url=profile_url_for(ig),
            status=ProfileStatus.ACTIVE,
            student={},
        )

    _apply_student_fields(
        profile,
        student_id=sid,
        instagram_username=ig,
        full_name=payload.full_name or None,
        university=payload.university or None,
    )
    if profile.id:
        await profile.save()
    else:
        await profile.insert()

    user = await _sync_linked_user(profile)
    if payload.grant:
        user = await ensure_student_user(profile, is_active=True)
    return _to_row(profile, user)
