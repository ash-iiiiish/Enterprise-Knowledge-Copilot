"""/chat endpoints: run a question through the async LangGraph workflow as the
signed-in user.

Thread continuity: no thread_id -> a new thread is created (titled from the
question); with one, the stored history is fed into the graph so follow-ups
resolve. Threads are private to their owner.
"""
import asyncio
import json
from typing import Any, Dict, Tuple

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.api.schemas import ChatRequest, ChatResponse
from app.logging_config import logger
from app.security import get_current_user
from db.models import User
from db.thread_repository import create_thread, get_messages, owns_thread
from graph.nodes import UI_CARD_TOOLS
from graph.workflow import get_app

router = APIRouter(tags=["chat"])

_TYPING_DELAY = 0.015  # seconds between word-chunks of the typed-out answer


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _actor(user: User) -> Dict[str, str]:
    return {"id": user.id, "employee_id": user.employee_id, "name": user.name, "role": user.role}


async def _prepare(payload: ChatRequest, user: User) -> Tuple[Dict[str, Any], str]:
    if payload.thread_id:
        if not await owns_thread(payload.thread_id, user.id):
            raise HTTPException(404, "Conversation not found")
        history = [
            {"role": m["role"], "content": m["content"]} for m in await get_messages(payload.thread_id, user.id)
        ]
        thread_id = payload.thread_id
    else:
        thread_id = await create_thread(payload.question, user.id)
        history = []
    inputs = {
        "question": payload.question,
        "thread_id": thread_id,
        "chat_history": history,
        "user": _actor(user),
    }
    return inputs, thread_id


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, user: User = Depends(get_current_user)) -> ChatResponse:
    inputs, thread_id = await _prepare(payload, user)
    logger.info(f"{user.employee_id} asked: {payload.question!r} (thread={thread_id})")
    try:
        result = await get_app().ainvoke(inputs)
    except Exception as exc:
        logger.exception("Graph execution failed")
        raise HTTPException(500, str(exc)) from exc

    tool_used = result.get("tool_used")
    envelope = result.get("tool_results") or {}
    return ChatResponse(
        question=payload.question,
        answer=result.get("final_answer", ""),
        sources=result.get("sources", []),
        tool_used=tool_used,
        tool_result=envelope.get("result") if tool_used in UI_CARD_TOOLS else None,
        verification=result.get("verification", ""),
        thread_id=thread_id,
    )


@router.post("/chat/stream")
async def chat_stream(payload: ChatRequest, user: User = Depends(get_current_user)):
    """SSE counterpart to /chat. Drives the same compiled graph (CRAG and
    Self-RAG loops included); persistence happens inside the graph.

    Events:
      routing   -> {"query_type", "need_retrieval", "need_tools"}
      tool_call -> {"tool_used", "arguments", "result"?}   result only for task tools
      retry     -> {"stage"}   rewriting_query | web_search_fallback | revising_answer
      token     -> {"text"}    typed-out, already-verified answer
      done      -> {"sources", "tool_used", "tool_result", "verification", "thread_id"}
      error     -> {"detail"}
    """
    inputs, thread_id = await _prepare(payload, user)

    async def event_stream():
        try:
            yield _sse("thread", {"thread_id": thread_id})
            final_state: dict = {}
            seen_verify_failure = False

            async for update in get_app().astream(inputs, stream_mode="updates"):
                for node_name, node_output in update.items():
                    node_output = node_output or {}  # nodes that return {} surface as None
                    final_state.update(node_output)

                    if node_name == "classify_query":
                        yield _sse("routing", {
                            "query_type": node_output.get("query_type"),
                            "need_retrieval": node_output.get("need_retrieval", False),
                            "need_tools": node_output.get("need_tools", False),
                        })
                    elif node_name in ("tool_route", "parallel_node") and node_output.get("tool_used"):
                        envelope = node_output.get("tool_results", {}) or {}
                        data = {"tool_used": node_output["tool_used"], "arguments": envelope.get("arguments", {})}
                        if node_output["tool_used"] in UI_CARD_TOOLS:
                            data["result"] = envelope.get("result")
                        yield _sse("tool_call", data)
                    elif node_name == "rewrite_query":
                        yield _sse("retry", {"stage": "revising_answer" if seen_verify_failure else "rewriting_query"})
                    elif node_name == "web_search":
                        yield _sse("retry", {"stage": "web_search_fallback"})
                    elif node_name == "verify_answer":
                        seen_verify_failure = str(node_output.get("verification", "")).upper() != "YES"

            for word in final_state.get("final_answer", "").split(" "):
                yield _sse("token", {"text": word + " "})
                await asyncio.sleep(_TYPING_DELAY)

            tool_used = final_state.get("tool_used")
            envelope = final_state.get("tool_results") or {}
            yield _sse("done", {
                "sources": final_state.get("sources", []),
                "tool_used": tool_used,
                "tool_result": envelope.get("result") if tool_used in UI_CARD_TOOLS else None,
                "verification": final_state.get("verification", ""),
                "thread_id": thread_id,
            })
        except Exception as exc:
            logger.exception("Streaming chat failed")
            yield _sse("error", {"detail": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
