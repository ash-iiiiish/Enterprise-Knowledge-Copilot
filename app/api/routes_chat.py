"""/chat endpoint: runs a question through the async LangGraph workflow.

Handles thread continuity: if no thread_id is given, a new thread is
created (titled from the question); if one is given, prior messages for
that thread are loaded and fed into the graph as chat_history so follow-up
questions resolve correctly.
"""
from fastapi import APIRouter, HTTPException

from app.api.schemas import ChatRequest, ChatResponse
from app.logging_config import logger
from db.thread_repository import create_thread, get_messages
from graph.workflow import get_app

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    app = get_app()
    logger.info(f"Incoming question: {payload.question!r} (thread_id={payload.thread_id})")

    if payload.thread_id:
        chat_history = [
            {"role": m["role"], "content": m["content"]} for m in await get_messages(payload.thread_id)
        ]
        thread_id = payload.thread_id
    else:
        thread_id = await create_thread(payload.question)
        chat_history = []

    try:
        result = await app.ainvoke(
            {
                "question": payload.question,
                "thread_id": thread_id,
                "chat_history": chat_history,
            }
        )
    except Exception as exc:
        logger.exception("Graph execution failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ChatResponse(
        question=payload.question,
        answer=result.get("final_answer", ""),
        sources=result.get("sources", []),
        verification=result.get("verification", ""),
        thread_id=thread_id,
    )
