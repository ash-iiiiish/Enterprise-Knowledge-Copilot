"""Shared LangGraph state definition for the Enterprise Knowledge Copilot."""
from typing import Any, Dict, List, TypedDict

from langchain_core.documents import Document


class State(TypedDict, total=False):
    question: str
    original_question: str  # preserved even if CRAG rewrites `question` for search

    # conversation / thread continuity
    thread_id: str
    chat_history: List[Dict[str, str]]  # [{"role": "user"|"assistant", "content": "..."}]

    # routing
    query_type: str
    need_retrieval: bool
    need_tools: bool

    # retrieval / tools
    rag_docs: List[Document]
    relevant_docs: List[Document]
    tool_results: Dict[str, Any]
    tool_used: str  # name of the MCP tool that was actually invoked, if any

    # context assembly
    rag_context: str
    tool_context: str
    final_context: str

    # generation / verification
    final_answer: str
    verification: str
    sources: List[str]

    # control flow
    retry_count: int
