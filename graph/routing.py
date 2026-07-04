"""Pure routing/decision functions for the LangGraph conditional edges.
Kept separate from graph/nodes.py so the branching logic is easy to unit test."""
from app.config import settings
from graph.state import State


def route_decision(state: State) -> str:
    """First fork after classify_query: decides which of the 4 sub-graphs to enter."""
    need_retrieval = state.get("need_retrieval", False)
    need_tools = state.get("need_tools", False)

    if need_retrieval and need_tools:
        return "both_path"
    if need_retrieval:
        return "retrieval_path"
    if need_tools:
        return "tool_path"
    return "direct_path"


def route_after_relevance(state: State) -> str:
    """CRAG-style fork: if no relevant docs were found (and we still have
    retries left), fall back to query rewrite + web search."""
    relevant_docs = state.get("relevant_docs", [])
    retry_count = state.get("retry_count", 0)

    if relevant_docs:
        return "valid"
    if retry_count >= settings.max_verification_retries:
        # out of retries: proceed anyway with whatever we have so the graph
        # always terminates instead of looping forever.
        return "valid"
    return "invalid"


def verify_answer_function(state: State) -> str:
    """Self-RAG verification fork: accept the answer, or loop back to
    rewrite/retry if the LLM says the answer isn't grounded in context."""
    verification = state.get("verification", "").lower()
    retry_count = state.get("retry_count", 0)

    if "yes" in verification:
        return "verified"
    if retry_count >= settings.max_verification_retries:
        return "verified"  # avoid infinite loops; ship the best-effort answer
    return "not_verified"
