from fastapi import APIRouter, Depends

from app.deps import get_current_user
from instascope_shared.models import Notification, User
from instascope_shared.schemas import MessageResponse, NotificationResponse

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationResponse])
async def list_notifications(user: User = Depends(get_current_user), unread_only: bool = False):
    query = Notification.find(Notification.user_id == str(user.id))
    items = await query.sort(-Notification.created_at).limit(50).to_list()
    if unread_only:
        items = [n for n in items if not n.is_read]
    return [
        NotificationResponse(
            id=str(n.id),
            profile_id=n.profile_id,
            type=n.type.value if hasattr(n.type, "value") else str(n.type),
            title=n.title,
            body=n.body,
            is_read=n.is_read,
            created_at=n.created_at,
            meta=n.meta,
        )
        for n in items
    ]


@router.post("/{notification_id}/read", response_model=MessageResponse)
async def mark_read(notification_id: str, user: User = Depends(get_current_user)):
    n = await Notification.get(notification_id)
    if n and n.user_id == str(user.id):
        n.is_read = True
        await n.save()
    return MessageResponse(message="Marked as read")


@router.post("/read-all", response_model=MessageResponse)
async def mark_all_read(user: User = Depends(get_current_user)):
    items = await Notification.find(
        Notification.user_id == str(user.id), Notification.is_read == False  # noqa: E712
    ).to_list()
    for n in items:
        n.is_read = True
        await n.save()
    return MessageResponse(message=f"Marked {len(items)} as read")
