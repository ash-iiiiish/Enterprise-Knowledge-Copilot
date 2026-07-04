"""Unit tests for the pure routing functions (no LLM/DB calls needed)."""
from graph.routing import route_after_relevance, route_decision, verify_answer_function


def test_route_decision_direct():
    assert route_decision({}) == "direct_path"


def test_route_decision_retrieval_only():
    assert route_decision({"need_retrieval": True}) == "retrieval_path"


def test_route_decision_tool_only():
    assert route_decision({"need_tools": True}) == "tool_path"


def test_route_decision_both():
    assert route_decision({"need_retrieval": True, "need_tools": True}) == "both_path"


def test_route_after_relevance_valid():
    assert route_after_relevance({"relevant_docs": [object()]}) == "valid"


def test_route_after_relevance_invalid_with_retries_left():
    assert route_after_relevance({"relevant_docs": [], "retry_count": 0}) == "invalid"


def test_route_after_relevance_forces_valid_when_out_of_retries():
    assert route_after_relevance({"relevant_docs": [], "retry_count": 99}) == "valid"


def test_verify_answer_function_verified():
    assert verify_answer_function({"verification": "YES, fully supported."}) == "verified"


def test_verify_answer_function_not_verified():
    assert verify_answer_function({"verification": "NO", "retry_count": 0}) == "not_verified"


def test_verify_answer_function_caps_retries():
    assert verify_answer_function({"verification": "NO", "retry_count": 99}) == "verified"
