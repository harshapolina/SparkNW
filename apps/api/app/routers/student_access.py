from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.deps import require_admin
from instascope_shared.models import DEFAULT_ORG_ID, User
from instascope_shared.schemas import (
    StudentAccessCreateRequest,
    StudentAccessListResponse,
    StudentAccessRow,
    StudentAccessUpdateRequest,
)
from instascope_shared.services import student_access as access_service

router = APIRouter(prefix="/spark/admin/student-access", tags=["student-access"])


def _org_id(user: User) -> str:
    return getattr(user, "org_id", None) or DEFAULT_ORG_ID


@router.get("", response_model=StudentAccessListResponse)
async def list_student_access(
    q: Optional[str] = Query(None),
    access: str = Query("all"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: User = Depends(require_admin),
):
    return await access_service.list_student_access(
        _org_id(user),
        q=q,
        access=access,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=StudentAccessRow, status_code=201)
async def create_student_access(
    payload: StudentAccessCreateRequest,
    user: User = Depends(require_admin),
):
    return await access_service.create_student_access(_org_id(user), str(user.id), payload)


@router.patch("/{profile_id}", response_model=StudentAccessRow)
async def update_student_access(
    profile_id: str,
    payload: StudentAccessUpdateRequest,
    user: User = Depends(require_admin),
):
    return await access_service.update_student_access(_org_id(user), profile_id, payload)
