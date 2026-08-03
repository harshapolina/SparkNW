from datetime import datetime

from fastapi import APIRouter, Depends

from app.deps import get_current_user
from instascope_shared.models import User, UserSettings
from instascope_shared.schemas import SettingsResponse, SettingsUpdateRequest

router = APIRouter(prefix="/settings", tags=["settings"])


async def _get_or_create(user_id: str) -> UserSettings:
    settings = await UserSettings.find_one(UserSettings.user_id == user_id)
    if not settings:
        settings = UserSettings(user_id=user_id)
        await settings.insert()
    return settings


@router.get("", response_model=SettingsResponse)
async def get_settings(user: User = Depends(get_current_user)):
    s = await _get_or_create(str(user.id))
    return SettingsResponse(
        dark_mode=s.dark_mode,
        follower_growth_notify_pct=s.follower_growth_notify_pct,
        notify_followers_down=s.notify_followers_down,
        notify_scrape_failed=s.notify_scrape_failed,
        notify_engagement_spike=s.notify_engagement_spike,
        engagement_spike_pct=s.engagement_spike_pct,
        timezone=s.timezone,
    )


@router.patch("", response_model=SettingsResponse)
async def update_settings(payload: SettingsUpdateRequest, user: User = Depends(get_current_user)):
    s = await _get_or_create(str(user.id))
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(s, k, v)
    s.updated_at = datetime.utcnow()
    await s.save()
    return SettingsResponse(
        dark_mode=s.dark_mode,
        follower_growth_notify_pct=s.follower_growth_notify_pct,
        notify_followers_down=s.notify_followers_down,
        notify_scrape_failed=s.notify_scrape_failed,
        notify_engagement_spike=s.notify_engagement_spike,
        engagement_spike_pct=s.engagement_spike_pct,
        timezone=s.timezone,
    )
