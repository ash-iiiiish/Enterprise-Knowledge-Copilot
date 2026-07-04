"""
Builds and compiles the LangGraph workflow:

  START -> classify_query -> (direct | retrieval | tool | both)
       direct:    generate_direct -> persist_turn -> END
       retrieval: enterprise_retrieve -> is_relevant -> (valid: generate_from_context
                    | invalid: rewrite_query -> web_search -> is_relevant [loop])
                  -> verify_answer -> (verified: attach_sources -> persist_turn -> END
                    | not_verified: rewrite_query -> web_search -> is_relevant [loop])
       tool:      tool_route -> generate_from_tool -> verify_answer -> ...
       both:      parallel_node -> merge_node -> verify_answer -> ...

All node functions are async, so the compiled graph must be driven with
`await app.ainvoke(...)` / `await app.astream(...)`.
"""
from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from graph import nodes
from graph.routing import route_after_relevance, route_decision, verify_answer_function
from graph.state import State


def build_graph():
    g = StateGraph(State)

    g.add_node("classify_query", nodes.classify_query)
    g.add_node("generate_direct", nodes.generate_direct)
    g.add_node("enterprise_retrieve", nodes.enterprise_retrieve)
    g.add_node("is_relevant", nodes.is_relevant)
    g.add_node("generate_from_context", nodes.generate_from_context)
    g.add_node("rewrite_query", nodes.rewrite_query_node)
    g.add_node("web_search", nodes.web_search_node)
    g.add_node("tool_route", nodes.tool_route)
    g.add_node("generate_from_tool", nodes.generate_from_tool)
    g.add_node("verify_answer", nodes.verify_answer)
    g.add_node("attach_sources", nodes.attach_sources)
    g.add_node("persist_turn", nodes.persist_turn)
    g.add_node("parallel_node", nodes.parallel_node)
    g.add_node("merge_node", nodes.merge_node)

    g.add_edge(START, "classify_query")

    g.add_conditional_edges(
        "classify_query",
        route_decision,
        {
            "direct_path": "generate_direct",
            "retrieval_path": "enterprise_retrieve",
            "tool_path": "tool_route",
            "both_path": "parallel_node",
        },
    )

    # direct path: no context to verify, straight to persistence
    g.add_edge("generate_direct", "persist_turn")

    # retrieval / CRAG path
    g.add_edge("enterprise_retrieve", "is_relevant")
    g.add_conditional_edges(
        "is_relevant",
        route_after_relevance,
        {
            "valid": "generate_from_context",
            "invalid": "rewrite_query",
        },
    )
    g.add_edge("rewrite_query", "web_search")
    g.add_edge("web_search", "is_relevant")
    g.add_edge("generate_from_context", "verify_answer")

    # tool-only path
    g.add_edge("tool_route", "generate_from_tool")
    g.add_edge("generate_from_tool", "verify_answer")

    # combined RAG + tool path
    g.add_edge("parallel_node", "merge_node")
    g.add_edge("merge_node", "verify_answer")

    # shared verification fork
    g.add_conditional_edges(
        "verify_answer",
        verify_answer_function,
        {
            "verified": "attach_sources",
            "not_verified": "rewrite_query",
        },
    )

    g.add_edge("attach_sources", "persist_turn")
    g.add_edge("persist_turn", END)

    return g.compile()


@lru_cache
def get_app():
    """Cached compiled graph - build once per process."""
    return build_graph()
