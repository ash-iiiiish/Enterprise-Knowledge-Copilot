"""
Async repository for chat threads/messages, scoped per user.

Powers the sidebar: listing past threads, loading a thread's history when the
user switches to it, and appending new turns as the conversation continues.
"""
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, func, select, update

from db.models import Message, Thread
from db.session import get_session


def _make_title(question: str, max_len: int = 60) -> str:
    question = " ".join(question.split())
    return question if len(question) <= max_len else question[: max_len - 1].rstrip() + "…"


async def create_thread(first_question: str, user_id: str) -> str:
    async with get_session() as session:
        thread = Thread(title=_make_title(first_question), user_id=user_id)
        session.add(thread)
        await session.flush()
        return thread.id


async def owns_thread(thread_id: str, user_id: str) -> bool:
    async with get_session() as session:
        res = await session.execute(
            select(Thread.id).where(Thread.id == thread_id, Thread.user_id == user_id)
        )
        return res.scalar_one_or_none() is not None


async def list_threads(user_id: str) -> List[Dict[str, Any]]:
    async with get_session() as session:
        stmt = select(Thread).where(Thread.user_id == user_id).order_by(Thread.updated_at.desc())
        threads = (await session.execute(stmt)).scalars().all()
        return [
            {
                "id": t.id,
                "title": t.title,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            }
            for t in threads
        ]


async def get_messages(thread_id: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Messages of a thread. When `user_id` is given, returns [] unless that
    user owns the thread (so one employee can't read another's chats)."""
    async with get_session() as session:
        if user_id is not None:
            owner = await session.execute(
                select(Thread.id).where(Thread.id == thread_id, Thread.user_id == user_id)
            )
            if owner.scalar_one_or_none() is None:
                return []
        stmt = select(Message).where(Message.thread_id == thread_id).order_by(Message.created_at.asc())
        messages = (await session.execute(stmt)).scalars().all()
        return [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "sources": m.sources or [],
                "verification": m.verification,
                "tool_used": m.tool_used,
                "tool_result": m.tool_result,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ]


async def add_message(
    thread_id: str,
    role: str,
    content: str,
    sources: Optional[List[str]] = None,
    verification: str = "",
    tool_used: Optional[str] = None,
    tool_result: Any = None,
) -> str:
    async with get_session() as session:
        message = Message(
            thread_id=thread_id,
            role=role,
            content=content,
            sources=sources or [],
            verification=verification,
            tool_used=tool_used,
            tool_result=tool_result,
        )
        session.add(message)
        await session.flush()
        await session.execute(
            update(Thread).where(Thread.id == thread_id).values(updated_at=func.now())
        )
        return message.id


async def delete_thread(thread_id: str, user_id: str) -> None:
    if not await owns_thread(thread_id, user_id):
        return
    async with get_session() as session:
        await session.execute(delete(Message).where(Message.thread_id == thread_id))
        await session.execute(delete(Thread).where(Thread.id == thread_id))


async def rename_thread(thread_id: str, title: str, user_id: str) -> None:
    async with get_session() as session:
        await session.execute(
            update(Thread).where(Thread.id == thread_id, Thread.user_id == user_id).values(title=title)
        )
