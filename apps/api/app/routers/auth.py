from fastapi import APIRouter, Depends, Request, status

from app.auth_rate_limit import enforce_auth_rate_limit
from app.deps import get_current_user
from instascope_shared.models import User
from instascope_shared.schemas import (
    AuthResponse,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    SignupRequest,
    StudentLoginRequest,
    TokenResponse,
    UserResponse,
)
from instascope_shared.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def signup(payload: SignupRequest, request: Request):
    enforce_auth_rate_limit(request, limit=5)
    return await auth_service.signup(payload)


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest, request: Request):
    enforce_auth_rate_limit(request)
    return await auth_service.login(payload)


@router.post("/student-login", response_model=AuthResponse)
async def student_login(payload: StudentLoginRequest, request: Request):
    enforce_auth_rate_limit(request)
    return await auth_service.student_login(payload)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: dict):
    token = payload.get("refresh_token")
    if not token:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="refresh_token required")
    return await auth_service.refresh_tokens(token)


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(payload: ForgotPasswordRequest):
    await auth_service.request_password_reset(payload.email)
    return MessageResponse(message="If that email exists, a reset link has been sent.")


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    return auth_service.user_response(user)
