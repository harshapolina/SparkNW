from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query

from app.deps import get_current_user, require_admin, require_student
from instascope_shared.models import DEFAULT_ORG_ID, User
from instascope_shared.services import spark as spark_service

router = APIRouter(prefix="/spark", tags=["spark"])

SortKey = Literal["overall", "points", "followers", "views", "engagement"]


def _org_id(user: User) -> str:
    return getattr(user, "org_id", None) or DEFAULT_ORG_ID


@router.get("/top-10")
async def top_10():
    """Public anonymous Top 10 — no auth, no personalized YOU row."""
    return await spark_service.get_top_10(DEFAULT_ORG_ID)


@router.get("/leaderboard")
async def leaderboard(
    sort: SortKey = Query("overall"),
    campus: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
):
    you_id = getattr(user, "profile_id", None)
    rows = await spark_service.build_leaderboard(_org_id(user), sort=sort, you_profile_id=you_id)
    if campus and campus.lower() not in {"all", "national", ""}:
        rows = [r for r in rows if r["campus"].lower() == campus.lower()]
        for i, r in enumerate(rows):
            r["rank"] = i + 1
            r["is_you"] = bool(you_id and r["id"] == you_id)
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
            r["is_you"] = bool(you_id and r["id"] == you_id)

    full = await spark_service.build_leaderboard(_org_id(user), sort=sort, you_profile_id=you_id)
    campuses = sorted({r["campus"] for r in full})
    you = next((r for r in full if r.get("is_you")), None)
    return {
        "items": rows,
        "total": len(rows),
        "campuses": campuses,
        "sort": sort,
        "you": you,
        "in_top_10": bool(you and you.get("rank", 999) <= 10),
    }


@router.get("/student")
async def student_dashboard(user: User = Depends(require_student)):
    profile_id = getattr(user, "profile_id", None)
    if not profile_id:
        return {"empty": True, "creators": [], "creator": None, "error": "No linked profile"}
    return await spark_service.get_student_dashboard(_org_id(user), profile_id)


@router.get("/admin")
async def admin_overview(user: User = Depends(require_admin)):
    return await spark_service.get_admin_overview(_org_id(user))
