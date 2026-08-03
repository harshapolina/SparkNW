from fastapi import APIRouter, Depends

from app.deps import get_current_user
from instascope_shared.models import User
from instascope_shared.schemas import OverviewResponse, ProfileAnalyticsResponse
from instascope_shared.services import analytics as analytics_service
from instascope_shared.services import profiles as profile_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview", response_model=OverviewResponse)
async def overview(user: User = Depends(get_current_user)):
    return await analytics_service.get_overview(str(user.id))


@router.get("/profiles/{profile_id}", response_model=ProfileAnalyticsResponse)
async def profile_analytics(profile_id: str, user: User = Depends(get_current_user)):
    await profile_service.get_profile(str(user.id), profile_id)
    return await analytics_service.get_profile_analytics(str(user.id), profile_id)
