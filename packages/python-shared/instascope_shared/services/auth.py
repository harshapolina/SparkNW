"""Auth service — signup, login, student login, password reset token stub."""

from __future__ import annotations

import re
import secrets
from datetime import datetime

from fastapi import HTTPException, status

from instascope_shared.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from instascope_shared.domain.instagram import extract_username
from instascope_shared.models import DEFAULT_ORG_ID, Profile, User, UserRole, UserSettings
from instascope_shared.schemas import (
    AuthResponse,
    LoginRequest,
    SignupRequest,
    StudentLoginRequest,
    TokenResponse,
    UserResponse,
)


def _role_value(user: User) -> str:
    role = getattr(user, "role", None)
    if isinstance(role, UserRole):
        return role.value
    if isinstance(role, str) and role:
        return role
    return UserRole.ADMIN.value


def user_response(user: User) -> UserResponse:
    return UserResponse(
        id=str(user.id),
        email=user.email,
        name=user.name,
        avatar_url=user.avatar_url,
        role=_role_value(user),
        org_id=getattr(user, "org_id", None) or DEFAULT_ORG_ID,
        profile_id=getattr(user, "profile_id", None),
        student_id=getattr(user, "student_id", None),
        created_at=user.created_at,
    )


def _user_response(user: User) -> UserResponse:
    return user_response(user)


def _tokens_for(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(str(user.id), user.email),
        refresh_token=create_refresh_token(str(user.id)),
    )


def _norm_student_id(raw: str) -> str:
    return re.sub(r"\s+", "", (raw or "").strip().upper())


def _norm_ig_username(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    try:
        extracted = extract_username(text)
        return extracted
    except ValueError:
        username = text.lstrip("@").strip().lower()
        username = username.split("?")[0].split("/")[0]
        return username


def _exact_ci(value: str) -> dict:
    return {"$regex": f"^{re.escape(value)}$", "$options": "i"}


def _profile_matches_login(profile: Profile, sid: str, ig: str) -> bool:
    student = getattr(profile, "student", None) or {}
    roster_sid = _norm_student_id(str(student.get("student_id") or ""))
    if roster_sid != sid:
        return False
    candidates = {
        _norm_ig_username(getattr(profile, "username", None) or ""),
        _norm_ig_username(str(student.get("instagram_username") or "")),
        _norm_ig_username(str(student.get("instagram_handle") or "")),
        _norm_ig_username(str(student.get("instagram_url") or "")),
    }
    candidates.discard("")
    return ig in candidates


async def signup(payload: SignupRequest) -> AuthResponse:
    existing = await User.find_one(User.email == payload.email.lower())
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        name=payload.name.strip(),
        role=UserRole.ADMIN,
        org_id=DEFAULT_ORG_ID,
    )
    await user.insert()
    await UserSettings(user_id=str(user.id)).insert()

    return AuthResponse(user=_user_response(user), tokens=_tokens_for(user))


async def login(payload: LoginRequest) -> AuthResponse:
    user = await User.find_one(User.email == payload.email.lower())
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
    if _role_value(user) == UserRole.STUDENT.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Students must sign in with student ID and Instagram handle",
        )

    # Backfill role/org for legacy accounts
    dirty = False
    if not getattr(user, "role", None):
        user.role = UserRole.ADMIN
        dirty = True
    if not getattr(user, "org_id", None):
        user.org_id = DEFAULT_ORG_ID
        dirty = True
    if dirty:
        user.updated_at = datetime.utcnow()
        await user.save()

    return AuthResponse(user=_user_response(user), tokens=_tokens_for(user))


def _student_email(student_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._+-]", "", student_id.lower()) or "student"
    # Use example.com — EmailStr rejects reserved TLDs like .local
    return f"{safe}@students.spark.example.com"


async def _find_student_profile(student_id: str, ig_username: str, org_id: str = DEFAULT_ORG_ID) -> Profile:
    sid = _norm_student_id(student_id)
    ig = _norm_ig_username(ig_username)
    if not sid or not ig:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="student_id and instagram_username are required",
        )

    # Look up one student by ID / handle. Never load the full roster.
    sid_rx = _exact_ci(sid)
    ig_rx = _exact_ci(ig)
    org_clause = {
        "$or": [
            {"org_id": org_id},
            {"org_id": {"$exists": False}},
            {"org_id": None},
            {"org_id": ""},
        ]
    }
    identity_clause = {
        "$or": [
            {"username": ig_rx},
            {"student.instagram_username": ig_rx},
            {"student.instagram_handle": ig_rx},
            {"student.student_id": sid_rx},
        ]
    }
    profiles = await Profile.find({"$and": [org_clause, identity_clause]}).to_list()
    matches = [p for p in profiles if _profile_matches_login(p, sid, ig)]

    if not matches:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No matching student profile for that student ID and Instagram handle",
        )
    if len(matches) > 1:
        # Prefer exact username match
        exact = [p for p in matches if _norm_ig_username(p.username or "") == ig]
        matches = exact or matches
    return matches[0]


async def student_login(payload: StudentLoginRequest) -> AuthResponse:
    profile = await _find_student_profile(payload.student_id, payload.instagram_username)
    sid = _norm_student_id(payload.student_id)
    org_id = getattr(profile, "org_id", None) or DEFAULT_ORG_ID
    if not getattr(profile, "org_id", None):
        profile.org_id = org_id
        profile.updated_at = datetime.utcnow()
        await profile.save()

    student = profile.student or {}
    display_name = (
        (student.get("full_name") if isinstance(student.get("full_name"), str) else None)
        or profile.full_name
        or profile.username
    )

    user = await User.find_one(User.profile_id == str(profile.id), User.role == UserRole.STUDENT)
    if not user:
        user = await User.find_one(User.student_id == sid, User.role == UserRole.STUDENT)

    if user:
        user.profile_id = str(profile.id)
        user.student_id = sid
        user.org_id = org_id
        user.name = str(display_name)
        user.avatar_url = profile.avatar_url
        user.updated_at = datetime.utcnow()
        await user.save()
    else:
        email = _student_email(sid)
        existing_email = await User.find_one(User.email == email)
        if existing_email:
            if _role_value(existing_email) == UserRole.STUDENT.value:
                user = existing_email
                user.profile_id = str(profile.id)
                user.student_id = sid
                user.org_id = org_id
                user.name = str(display_name)
                user.avatar_url = profile.avatar_url
                user.updated_at = datetime.utcnow()
                await user.save()
            else:
                email = f"{sid.lower()}.{secrets.token_hex(3)}@students.spark.example.com"
                user = None
        if not user:
            user = User(
                email=email,
                # Students never use password login; skip bcrypt (~300ms) on first sign-in.
                password_hash="!",
                name=str(display_name),
                role=UserRole.STUDENT,
                org_id=org_id,
                profile_id=str(profile.id),
                student_id=sid,
                avatar_url=profile.avatar_url,
            )
            await user.insert()
            await UserSettings(user_id=str(user.id)).insert()

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    return AuthResponse(user=_user_response(user), tokens=_tokens_for(user))


async def refresh_tokens(refresh_token: str) -> TokenResponse:
    data = decode_token(refresh_token)
    if not data or data.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user = await User.get(data["sub"])
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return _tokens_for(user)


async def request_password_reset(email: str) -> str:
    """Returns a reset token if user exists (never reveal existence to client)."""
    user = await User.find_one(User.email == email.lower())
    if not user:
        return ""
    from datetime import timedelta

    from instascope_shared.core.security import create_token

    return create_token(
        str(user.id),
        token_type="password_reset",
        expires_delta=timedelta(hours=1),
    )


async def get_user_by_id(user_id: str) -> User:
    user = await User.get(user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    return user


def touch_user(user: User) -> None:
    user.updated_at = datetime.utcnow()
