from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query

from app.deps import get_current_user
from instascope_shared.models import User
from instascope_shared.services import spark as spark_service

router = APIRouter(prefix="/spark", tags=["spark"])

SortKey = Literal["overall", "points", "followers", "views", "engagement"]


@router.get("/leaderboard")
async def leaderboard(
    sort: SortKey = Query("overall"),
    campus: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
):
    rows = await spark_service.build_leaderboard(str(user.id), sort=sort)
    if campus and campus.lower() not in {"all", "national", ""}:
        rows = [r for r in rows if r["campus"].lower() == campus.lower()]
        for i, r in enumerate(rows):
            r["rank"] = i + 1
    if q:
        s = q.lower().strip()
        rows = [
            r
            for r in rows
            if s in r["name"].lower()
            or s in r["handle"].lower()
            or s in r["campus"].lower()
            or s in (r.get("team") or "").lower()
        ]
        for i, r in enumerate(rows):
            r["rank"] = i + 1
    campuses = sorted({r["campus"] for r in await spark_service.build_leaderboard(str(user.id))})
    return {"items": rows, "total": len(rows), "campuses": campuses, "sort": sort}


@router.get("/student")
async def student_dashboard(
    profile_id: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
):
    return await spark_service.get_student_dashboard(str(user.id), profile_id)


@router.get("/admin")
async def admin_overview(user: User = Depends(get_current_user)):
    return await spark_service.get_admin_overview(str(user.id))
