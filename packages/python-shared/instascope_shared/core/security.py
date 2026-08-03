"""Password hashing and JWT helpers."""

from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from instascope_shared.core.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_token(
    subject: str,
    *,
    token_type: str,
    expires_delta: timedelta,
    extra: dict[str, Any] | None = None,
) -> str:
    settings = get_settings()
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "exp": datetime.now(UTC) + expires_delta,
        "iat": datetime.now(UTC),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: str, email: str) -> str:
    settings = get_settings()
    return create_token(
        user_id,
        token_type="access",
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
        extra={"email": email},
    )


def create_refresh_token(user_id: str) -> str:
    settings = get_settings()
    return create_token(
        user_id,
        token_type="refresh",
        expires_delta=timedelta(days=settings.refresh_token_expire_days),
    )


def decode_token(token: str) -> dict[str, Any] | None:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
