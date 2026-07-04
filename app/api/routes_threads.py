"""Thread history endpoints: powers the sidebar list, switching between
past conversations, and continuing them."""
from typing import List

from fastapi import APIRouter, HTTPException

from app.api.schemas import MessageOut, RenameThreadRequest, ThreadSummary
from db.thread_repository import delete_thread, get_messages, list_threads, rename_thread

router = APIRouter(tags=["threads"])


@router.get("/threads", response_model=List[ThreadSummary])
async def get_threads() -> List[ThreadSummary]:
    return [ThreadSummary(**t) for t in await list_threads()]


@router.get("/threads/{thread_id}/messages", response_model=List[MessageOut])
async def get_thread_messages(thread_id: str) -> List[MessageOut]:
    messages = await get_messages(thread_id)
    if not messages:
        # not an error - a brand-new thread has no messages yet
        return []
    return [MessageOut(**m) for m in messages]


@router.patch("/threads/{thread_id}")
async def patch_thread(thread_id: str, payload: RenameThreadRequest) -> dict:
    await rename_thread(thread_id, payload.title)
    return {"status": "renamed"}


@router.delete("/threads/{thread_id}")
async def remove_thread(thread_id: str) -> dict:
    await delete_thread(thread_id)
    return {"status": "deleted"}
