"""FastAPI dependency injection — current user from JWT + role gates."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from instascope_shared.core.security import decode_token
from instascope_shared.models import User, UserRole
from instascope_shared.services import auth as auth_service

bearer = HTTPBearer(auto_error=False)


def _role_of(user: User) -> str:
    role = getattr(user, "role", None)
    if isinstance(role, UserRole):
        return role.value
    if isinstance(role, str) and role:
        return role
    return UserRole.ADMIN.value


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> User:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = decode_token(credentials.credentials)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return await auth_service.get_user_by_id(payload["sub"])


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if _role_of(user) != UserRole.ADMIN.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


async def require_student(user: User = Depends(get_current_user)) -> User:
    if _role_of(user) != UserRole.STUDENT.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Student access required")
    return user
