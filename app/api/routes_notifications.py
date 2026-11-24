"""In-app notification inbox (the bell icon). The UI polls /notifications."""
from fastapi import APIRouter, Depends

from app.security import get_current_user
from db import task_repository as repo
from db.models import User

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
async def inbox(unread_only: bool = False, user: User = Depends(get_current_user)) -> dict:
    return await repo.list_notifications(user.id, unread_only=unread_only)


@router.post("/read-all")
async def read_all(user: User = Depends(get_current_user)) -> dict:
    await repo.mark_all_read(user.id)
    return {"status": "ok"}


@router.post("/{notification_id}/read")
async def read_one(notification_id: int, user: User = Depends(get_current_user)) -> dict:
    await repo.mark_notification_read(user.id, notification_id)
    return {"status": "ok"}
