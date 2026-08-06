from datetime import datetime, time
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps import get_current_user, require_admin, require_student
from instascope_shared.models import DEFAULT_ORG_ID, User
from instascope_shared.services import spark as spark_service

router = APIRouter(prefix="/spark", tags=["spark"])

SortKey = Literal["overall", "points", "followers", "views", "engagement"]


def _org_id(user: User) -> str:
    return getattr(user, "org_id", None) or DEFAULT_ORG_ID


def _parse_leaderboard_day(raw: Optional[str], *, end_of_day: bool = False) -> Optional[datetime]:
    """Parse YYYY-MM-DD into a naive datetime (start or end of that UTC day)."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        day = datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="from_date/to_date must be YYYY-MM-DD") from exc
    if end_of_day:
        return datetime.combine(day, time(23, 59, 59))
    return datetime.combine(day, time.min)


@router.get("/top-10")
async def top_10():
    """Public anonymous Top 10 — no auth, no personalized YOU row."""
    return await spark_service.get_top_10(DEFAULT_ORG_ID)


@router.get("/leaderboard")
async def leaderboard(
    sort: SortKey = Query("overall"),
    campus: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None, description="Inclusive start date YYYY-MM-DD"),
    to_date: Optional[str] = Query(None, description="Inclusive end date YYYY-MM-DD"),
    user: User = Depends(get_current_user),
):
    you_id = getattr(user, "profile_id", None)
    start = _parse_leaderboard_day(from_date, end_of_day=False)
    end = _parse_leaderboard_day(to_date, end_of_day=True)
    if start and end and start.date() > end.date():
        raise HTTPException(status_code=400, detail="from_date must be on or before to_date")

    applied_from = start.strftime("%Y-%m-%d") if start else None
    applied_to = end.strftime("%Y-%m-%d") if end else None

    rows = await spark_service.build_leaderboard(
        _org_id(user),
        sort=sort,
        you_profile_id=you_id,
        from_date=start,
        to_date=end,
    )
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

    # Campuses from the same date window (avoid a second full live board pass).
    campuses = sorted({r["campus"] for r in rows if r.get("campus")})
    # If campus/q filtered the list, rebuild campus list from unfiltered window board.
    if campus or q:
        full = await spark_service.build_leaderboard(
            _org_id(user),
            sort=sort,
            you_profile_id=you_id,
            from_date=start,
            to_date=end,
        )
        campuses = sorted({r["campus"] for r in full if r.get("campus")})
        you = next((r for r in full if r.get("is_you")), None)
    else:
        you = next((r for r in rows if r.get("is_you")), None)

    return {
        "items": rows,
        "total": len(rows),
        "campuses": campuses,
        "sort": sort,
        "you": you,
        "in_top_10": bool(you and you.get("rank", 999) <= 10),
        "from_date": applied_from,
        "to_date": applied_to,
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
