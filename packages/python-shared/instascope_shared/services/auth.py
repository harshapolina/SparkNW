"""Auth service — signup, login, password reset token stub."""

from datetime import datetime

from fastapi import HTTPException, status

from instascope_shared.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from instascope_shared.models import User, UserSettings
from instascope_shared.schemas import (
    AuthResponse,
    LoginRequest,
    SignupRequest,
    TokenResponse,
    UserResponse,
)


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        id=str(user.id),
        email=user.email,
        name=user.name,
        avatar_url=user.avatar_url,
        created_at=user.created_at,
    )


def _tokens_for(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(str(user.id), user.email),
        refresh_token=create_refresh_token(str(user.id)),
    )


async def signup(payload: SignupRequest) -> AuthResponse:
    existing = await User.find_one(User.email == payload.email.lower())
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        name=payload.name.strip(),
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
    # Production: email this token. For now return opaque JWT-style reset.
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
