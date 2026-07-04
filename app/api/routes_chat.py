"""/chat endpoint: runs a question through the async LangGraph workflow.

Handles thread continuity: if no thread_id is given, a new thread is
created (titled from the question); if one is given, prior messages for
that thread are loaded and fed into the graph as chat_history so follow-up
questions resolve correctly.
"""
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.api.schemas import ChatRequest, ChatResponse
from app.logging_config import logger
from db.thread_repository import add_message, create_thread, get_messages
from graph import nodes
from graph.routing import route_decision
from graph.workflow import get_app

router = APIRouter(tags=["chat"])


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


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
        tool_used=result.get("tool_used"),
        verification=result.get("verification", ""),
        thread_id=thread_id,
    )


@router.post("/chat/stream")
async def chat_stream(payload: ChatRequest):
    """Streaming counterpart to /chat: emits SSE events as the answer is
    produced instead of waiting for the whole graph run.

    Event sequence:
      routing   -> {"query_type", "need_retrieval", "need_tools"}
      tool_call -> {"tool_used", "arguments"}          (only if a tool ran)
      token     -> {"text"}                             (repeated, typed answer)
      done      -> {"sources", "verification", "thread_id"}
      error     -> {"detail"}

    Note: this path skips the CRAG/Self-RAG rewrite-and-retry loop (it always
    does a single retrieval/tool pass then streams the generation) so it can
    start emitting tokens immediately. Use /chat when you need the fully
    verified, retry-capable answer instead.
    """

    async def event_stream():
        try:
            if payload.thread_id:
                chat_history = [
                    {"role": m["role"], "content": m["content"]}
                    for m in await get_messages(payload.thread_id)
                ]
                thread_id = payload.thread_id
            else:
                thread_id = await create_thread(payload.question)
                chat_history = []

            state = {
                "question": payload.question,
                "original_question": payload.question,
                "thread_id": thread_id,
                "chat_history": chat_history,
            }

            classify_update = await nodes.classify_query(state)
            state.update(classify_update)
            yield _sse(
                "routing",
                {
                    "query_type": state.get("query_type"),
                    "need_retrieval": state.get("need_retrieval", False),
                    "need_tools": state.get("need_tools", False),
                },
            )

            path = route_decision(state)

            if path == "direct_path":
                pass  # no retrieval/tool context needed before streaming

            elif path == "retrieval_path":
                state.update(await nodes.enterprise_retrieve(state))
                state["relevant_docs"] = state.get("rag_docs", [])

            elif path == "tool_path":
                state.update(await nodes.tool_route(state))
                if state.get("tool_used"):
                    yield _sse(
                        "tool_call",
                        {
                            "tool_used": state["tool_used"],
                            "arguments": state.get("tool_results", {}).get("arguments", {}),
                        },
                    )

            else:  # both_path
                state.update(await nodes.parallel_node(state))
                if state.get("tool_used"):
                    yield _sse(
                        "tool_call",
                        {
                            "tool_used": state["tool_used"],
                            "arguments": state.get("tool_results", {}).get("arguments", {}),
                        },
                    )

            answer_chunks = []
            async for chunk in nodes.stream_final_answer(state):
                answer_chunks.append(chunk)
                yield _sse("token", {"text": chunk})

            final_answer = "".join(answer_chunks)
            sources = []
            if state.get("rag_context"):
                sources.append("vector_db")
            if state.get("tool_context"):
                tool_used = state.get("tool_used")
                sources.append(f"external_tools:{tool_used}" if tool_used else "external_tools")

            await add_message(thread_id, role="user", content=payload.question)
            await add_message(thread_id, role="assistant", content=final_answer, sources=sources)

            yield _sse(
                "done",
                {"sources": sources, "tool_used": state.get("tool_used"), "thread_id": thread_id},
            )

        except Exception as exc:
            logger.exception("Streaming chat failed")
            yield _sse("error", {"detail": str(exc)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
