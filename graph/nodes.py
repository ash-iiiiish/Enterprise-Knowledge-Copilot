"""
All LangGraph node implementations.

Every node is an `async def` coroutine. LangGraph natively awaits async node
functions, and every I/O call inside (LLM, DB, MCP, web search) is awaited
in turn, so a single graph run never blocks the event loop and multiple
runs (e.g. concurrent FastAPI requests) can be served in parallel.

Conversation continuity: `state["chat_history"]` (loaded from the DB by the
/chat route before the graph is invoked) is folded into every generation
prompt so follow-up questions ("what about the second one?") resolve
correctly. `persist_turn` is the final node and writes both the user
question and the assistant answer to the `messages` table for the active
thread, which is what makes "continue this chat later" possible.
"""
import asyncio
from typing import Any, Dict, List

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field, field_validator

from app.logging_config import logger
from core.llm import get_llm
from db.thread_repository import add_message
from db.vector_repository import search_documents
from graph.state import State
from ingestion.web_search import duckduckgo_search
from mcp_server.client import mcp_client

MAX_HISTORY_TURNS = 6  # last N messages folded into prompts, to bound token usage


def _answer_question(state: State) -> str:
    """The question the final answer should actually address - always the
    user's original wording, even if `question` was rewritten by CRAG for
    search purposes."""
    return state.get("original_question") or state["question"]


def _format_history(state: State) -> str:
    history: List[Dict[str, str]] = state.get("chat_history", [])
    if not history:
        return ""
    recent = history[-MAX_HISTORY_TURNS:]
    lines = [f"{turn['role'].upper()}: {turn['content']}" for turn in recent]
    return "Conversation so far:\n" + "\n".join(lines)


# --------------------------------------------------------------------------
# Query classification / routing
# --------------------------------------------------------------------------


def _coerce_bool(v: Any) -> Any:
    """Some Groq models emit "true"/"false" as strings instead of real JSON
    booleans for tool-call parameters, which Groq's own server-side schema
    validator rejects outright (400 tool_use_failed) before it ever reaches
    client-side Pydantic parsing. Using json_mode avoids the strict tool
    schema path entirely; this validator is a defensive second layer in
    case a string still slips through."""
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes")
    return v


class ClassifyQueryOutput(BaseModel):
    query_type: str = Field(
        ..., description="general_knowledge | retrieval_needed | tool_needed | both_needed"
    )
    need_retrieval: bool = Field(..., description="True if internal RAG documents are needed")
    need_tools: bool = Field(..., description="True if external tools/APIs are needed")

    @field_validator("need_retrieval", "need_tools", mode="before")
    @classmethod
    def _coerce(cls, v: Any) -> Any:
        return _coerce_bool(v)


_CLASSIFY_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a routing assistant for an enterprise AI system.\n"
            "Classify the query into: general_knowledge | retrieval_needed | "
            "tool_needed | both_needed.\n"
            "Rules:\n"
            "- If internal enterprise documents are needed -> need_retrieval = true\n"
            "- If external tools/APIs (tickets, employee lookup, policies) are needed "
            "-> need_tools = true\n"
            "- If both are needed, both must be true.\n"
            "Use the conversation history only to resolve follow-up questions "
            "(e.g. pronouns, 'the second one').\n"
            "Respond with a single JSON object with exactly these keys: "
            'query_type (string), need_retrieval (true/false), need_tools (true/false). '
            "need_retrieval and need_tools MUST be JSON booleans, not strings.",
        ),
        ("human", "{history}\n\nCurrent question: {question}"),
    ]
)


async def classify_query(state: State) -> Dict[str, Any]:
    llm = get_llm().with_structured_output(ClassifyQueryOutput, method="json_mode")
    out: ClassifyQueryOutput = await llm.ainvoke(
        _CLASSIFY_PROMPT.format_messages(question=state["question"], history=_format_history(state))
    )
    return {
        "query_type": out.query_type,
        "need_retrieval": out.need_retrieval,
        "need_tools": out.need_tools,
        "retry_count": 0,
        "original_question": state["question"],
    }


# --------------------------------------------------------------------------
# Direct (no-context) generation
# --------------------------------------------------------------------------

_DIRECT_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Answer using only general knowledge.\n"
            "Do not assume access to external documents.\n"
            "If unsure, say: I don't know based on my general knowledge.\n"
            "Use the conversation history for context on follow-up questions.",
        ),
        ("human", "{history}\n\nCurrent question: {question}"),
    ]
)


async def generate_direct(state: State) -> Dict[str, Any]:
    out = await get_llm().ainvoke(
        _DIRECT_PROMPT.format_messages(question=_answer_question(state), history=_format_history(state))
    )
    return {"final_answer": out.content, "final_context": "", "sources": []}


# --------------------------------------------------------------------------
# Retrieval (RAG) over the single enterprise knowledge base
# --------------------------------------------------------------------------


async def enterprise_retrieve(state: State) -> Dict[str, Any]:
    docs = await search_documents(state["question"], k=5)
    return {
        "rag_docs": docs,
        "rag_context": "\n".join(d.page_content for d in docs),
    }


class RelevanceDecision(BaseModel):
    is_relevant: bool = Field(...)

    @field_validator("is_relevant", mode="before")
    @classmethod
    def _coerce(cls, v: Any) -> Any:
        return _coerce_bool(v)


_RELEVANCE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Decide whether the document helps answer the question. "
            "Respond with a single JSON object with exactly one key: "
            "is_relevant, a JSON boolean (true/false, not a string).",
        ),
        ("human", "Question: {question}\nDocument: {document}"),
    ]
)


async def _grade_one(question: str, doc: Document) -> bool:
    llm = get_llm().with_structured_output(RelevanceDecision, method="json_mode")
    decision: RelevanceDecision = await llm.ainvoke(
        _RELEVANCE_PROMPT.format_messages(question=question, document=doc.page_content)
    )
    return decision.is_relevant


async def is_relevant(state: State) -> Dict[str, Any]:
    """CRAG document grading. All docs graded concurrently via asyncio.gather."""
    docs: List[Document] = state.get("rag_docs", [])
    if not docs:
        return {"relevant_docs": []}

    flags = await asyncio.gather(*[_grade_one(state["question"], d) for d in docs])
    relevant_docs = [d for d, keep in zip(docs, flags) if keep]
    return {"relevant_docs": relevant_docs}


_RAG_GENERATION_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Use ONLY the provided context to answer.\n"
            "If the context is insufficient, say: No relevant document found.\n"
            "Use the conversation history for context on follow-up questions.",
        ),
        ("human", "{history}\n\nQuestion: {question}\nContext: {context}"),
    ]
)


async def generate_from_context(state: State) -> Dict[str, Any]:
    docs: List[Document] = state.get("relevant_docs", [])
    context = "\n\n---\n\n".join(d.page_content for d in docs).strip()

    if not context:
        return {"final_answer": "No relevant document found.", "final_context": ""}

    out = await get_llm().ainvoke(
        _RAG_GENERATION_PROMPT.format_messages(
            question=_answer_question(state), context=context, history=_format_history(state)
        )
    )
    return {"final_answer": out.content, "final_context": context}


# --------------------------------------------------------------------------
# CRAG fallback: rewrite query + web search
# --------------------------------------------------------------------------

_REWRITE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Rewrite the user's question into a short, precise web-search query. "
            "Return only the rewritten query, nothing else.",
        ),
        ("human", "{question}"),
    ]
)


async def rewrite_query_node(state: State) -> Dict[str, Any]:
    out = await get_llm().ainvoke(_REWRITE_PROMPT.format_messages(question=state["question"]))
    retry_count = state.get("retry_count", 0) + 1
    logger.info(f"Rewriting query (attempt {retry_count}): {out.content}")
    return {"question": out.content.strip(), "retry_count": retry_count}


async def web_search_node(state: State) -> Dict[str, Any]:
    results = await duckduckgo_search(state["question"])
    web_docs = [Document(page_content=r, metadata={"source": "web_search"}) for r in results]

    existing_docs = state.get("rag_docs", [])
    merged_docs = existing_docs + web_docs
    return {
        "rag_docs": merged_docs,
        "rag_context": "\n".join(d.page_content for d in merged_docs),
    }


# --------------------------------------------------------------------------
# Tool path (MCP)
# --------------------------------------------------------------------------


async def tool_route(state: State) -> Dict[str, Any]:
    result = await mcp_client.route(state["question"])
    return {"tool_results": result, "tool_context": str(result)}


async def generate_from_tool(state: State) -> Dict[str, Any]:
    """Turn a raw MCP tool result into a natural-language answer."""
    tool_context = state.get("tool_context", "")
    out = await get_llm().ainvoke(
        _RAG_GENERATION_PROMPT.format_messages(
            question=_answer_question(state), context=tool_context, history=_format_history(state)
        )
    )
    return {"final_context": tool_context, "final_answer": out.content}


# --------------------------------------------------------------------------
# Combined RAG + tools path
# --------------------------------------------------------------------------


async def parallel_node(state: State) -> Dict[str, Any]:
    """Run retrieval and tool-calling concurrently instead of sequentially."""
    docs, tool_result = await asyncio.gather(
        search_documents(state["question"], k=5),
        mcp_client.route(state["question"]),
    )
    return {
        "rag_docs": docs,
        "tool_results": tool_result,
        "rag_context": "\n".join(d.page_content for d in docs),
        "tool_context": str(tool_result),
    }


async def merge_node(state: State) -> Dict[str, Any]:
    rag = state.get("rag_context", "")
    tool = state.get("tool_context", "")
    final_context = f"{rag}\n{tool}".strip()

    out = await get_llm().ainvoke(
        _RAG_GENERATION_PROMPT.format_messages(
            question=_answer_question(state), context=final_context, history=_format_history(state)
        )
    )
    return {"final_context": final_context, "final_answer": out.content}


# --------------------------------------------------------------------------
# Verification / sources / persistence
# --------------------------------------------------------------------------


async def verify_answer(state: State) -> Dict[str, Any]:
    context = state.get("final_context", "")
    question = _answer_question(state)
    prompt = (
        f"Question: {question}\n"
        f"Answer: {state.get('final_answer', '')}\n"
        f"Context: {context}\n"
        "Is the answer fully supported by the context? Respond with a single "
        "word: YES or NO."
    )
    response = await get_llm().ainvoke(prompt)
    return {"verification": response.content.strip()}


async def attach_sources(state: State) -> Dict[str, Any]:
    sources = []
    if state.get("rag_context"):
        sources.append("vector_db")
    if state.get("tool_context"):
        sources.append("external_tools")
    return {"sources": sources}


async def persist_turn(state: State) -> Dict[str, Any]:
    """Persist this turn (user question + assistant answer) to the active
    thread, so it shows up in the sidebar history and can be resumed later."""
    thread_id = state["thread_id"]

    await add_message(thread_id, role="user", content=_answer_question(state))
    await add_message(
        thread_id,
        role="assistant",
        content=state.get("final_answer", ""),
        sources=state.get("sources", []),
        verification=state.get("verification", ""),
    )
    return {}