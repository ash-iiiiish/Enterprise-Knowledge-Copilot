"""/chat endpoint: runs a question through the async LangGraph workflow.

Handles thread continuity: if no thread_id is given, a new thread is
created (titled from the question); if one is given, prior messages for
that thread are loaded and fed into the graph as chat_history so follow-up
questions resolve correctly.
"""
import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.api.schemas import ChatRequest, ChatResponse
from app.logging_config import logger
from db.thread_repository import create_thread, get_messages
from graph.workflow import get_app

router = APIRouter(tags=["chat"])

# Pause between word-chunks when "typing out" the final answer (seconds).
_TYPING_DELAY = 0.02


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
    """Streaming counterpart to /chat.

    This drives the *same compiled graph* as /chat (`get_app().astream(...,
    stream_mode="updates")`), so the CRAG relevance-grading loop and the
    Self-RAG verification retry loop both run exactly as they do there -
    nothing is skipped. `persist_turn` is a node in that graph, so it saves
    the turn to the DB itself; this route doesn't write to the DB directly.

    Streaming, not the retry loop, is the part that has to compromise: a
    verification retry can only happen *after* a full answer has been
    generated and checked, so we can't safely hand out raw LLM tokens as
    they're produced - an answer that fails verification and gets rewritten
    would otherwise already be sitting in the user's chat window. Instead,
    intermediate graph steps are surfaced live as they complete (routing,
    which tool ran, whether a retry/rewrite happened), and once the graph
    reaches its final, *verified* answer, that text is sent as a sequence of
    small "token" chunks with a short delay between them for a typed-out
    feel - a simulated typing effect over a real, fully-verified answer,
    rather than true token streaming over an unverified one.

    Event sequence:
      routing   -> {"query_type", "need_retrieval", "need_tools"}
      tool_call -> {"tool_used", "arguments"}       (whenever a tool runs, incl. on retries)
      retry     -> {"stage"}                          (rewriting_query | web_search_fallback | revising_answer)
      token     -> {"text"}                            (repeated, typed-out final answer)
      done      -> {"sources", "tool_used", "verification", "thread_id"}
      error     -> {"detail"}
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

            inputs = {
                "question": payload.question,
                "thread_id": thread_id,
                "chat_history": chat_history,
            }

            app = get_app()
            final_state: dict = {}
            seen_verify_failure = False

            async for update in app.astream(inputs, stream_mode="updates"):
                for node_name, node_output in update.items():
                    final_state.update(node_output)

                    if node_name == "classify_query":
                        yield _sse(
                            "routing",
                            {
                                "query_type": node_output.get("query_type"),
                                "need_retrieval": node_output.get("need_retrieval", False),
                                "need_tools": node_output.get("need_tools", False),
                            },
                        )

                    elif node_name in ("tool_route", "parallel_node") and node_output.get("tool_used"):
                        tool_results = node_output.get("tool_results", {}) or {}
                        yield _sse(
                            "tool_call",
                            {
                                "tool_used": node_output["tool_used"],
                                "arguments": tool_results.get("arguments", {}),
                            },
                        )

                    elif node_name == "rewrite_query":
                        stage = "revising_answer" if seen_verify_failure else "rewriting_query"
                        yield _sse("retry", {"stage": stage})

                    elif node_name == "web_search":
                        yield _sse("retry", {"stage": "web_search_fallback"})

                    elif node_name == "verify_answer":
                        seen_verify_failure = str(node_output.get("verification", "")).upper() != "YES"

            final_answer = final_state.get("final_answer", "")
            for word in final_answer.split(" "):
                yield _sse("token", {"text": word + " "})
                await asyncio.sleep(_TYPING_DELAY)

            yield _sse(
                "done",
                {
                    "sources": final_state.get("sources", []),
                    "tool_used": final_state.get("tool_used"),
                    "verification": final_state.get("verification", ""),
                    "thread_id": thread_id,
                },
            )

        except Exception as exc:
            logger.exception("Streaming chat failed")
            yield _sse("error", {"detail": str(exc)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
