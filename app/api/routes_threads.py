"""Thread history endpoints (per user): sidebar list, open, rename, delete."""
from typing import List

from fastapi import APIRouter, Depends

from app.api.schemas import MessageOut, RenameThreadRequest, ThreadSummary
from app.security import get_current_user
from db.models import User
from db.thread_repository import delete_thread, get_messages, list_threads, rename_thread

router = APIRouter(tags=["threads"])


@router.get("/threads", response_model=List[ThreadSummary])
async def get_threads(user: User = Depends(get_current_user)) -> List[ThreadSummary]:
    return [ThreadSummary(**t) for t in await list_threads(user.id)]


@router.get("/threads/{thread_id}/messages", response_model=List[MessageOut])
async def get_thread_messages(thread_id: str, user: User = Depends(get_current_user)) -> List[MessageOut]:
    return [MessageOut(**m) for m in await get_messages(thread_id, user.id)]


@router.patch("/threads/{thread_id}")
async def patch_thread(thread_id: str, payload: RenameThreadRequest, user: User = Depends(get_current_user)) -> dict:
    await rename_thread(thread_id, payload.title.strip()[:120] or "Untitled", user.id)
    return {"status": "renamed"}


@router.delete("/threads/{thread_id}")
async def remove_thread(thread_id: str, user: User = Depends(get_current_user)) -> dict:
    await delete_thread(thread_id, user.id)
    return {"status": "deleted"}
