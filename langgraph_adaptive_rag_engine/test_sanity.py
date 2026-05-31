"""Sanity tests — verify imports, Pydantic models, and basic logic without network."""
from __future__ import annotations

import sys
import os

# Ensure src is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from src.state import AgentState, HallucinationReport


def test_agent_state_defaults():
    state = AgentState()
    assert state.messages == []
    assert state.current_query == ""
    assert state.retrieved_docs == []
    assert state.search_count == 0
    assert state.is_relevant is False
    assert state.hallucination_report is None
    assert state.answer == ""
    print("[PASS] AgentState defaults OK")


def test_agent_state_mutation():
    state = AgentState(current_query="hello", is_relevant=True, search_count=2)
    d = state.model_dump()
    state2 = AgentState(**d)
    assert state2.current_query == "hello"
    assert state2.is_relevant is True
    assert state2.search_count == 2
    print("[PASS] AgentState mutation / round-trip OK")


def test_hallucination_report_valid():
    hr = HallucinationReport(score=0.3, ungrounded_claims=["claim1"], verdict="NOT_SUPPORTED")
    assert 0.0 <= hr.score <= 1.0
    assert hr.verdict == "NOT_SUPPORTED"
    print("[PASS] HallucinationReport valid OK")


def test_hallucination_report_boundaries():
    hr_min = HallucinationReport(score=0.0, verdict="SUPPORTED")
    hr_max = HallucinationReport(score=1.0, verdict="NOT_SUPPORTED")
    assert hr_min.score == 0.0
    assert hr_max.score == 1.0
    print("[PASS] HallucinationReport boundaries OK")


def test_doc_grade_model():
    from src.chains.doc_grader import DocGrade
    g = DocGrade(is_relevant=True, reasoning="matched keyword")
    assert g.is_relevant is True
    print("[PASS] DocGrade model OK")


def test_query_route_model():
    from src.chains.router import QueryRoute
    r = QueryRoute(destination="vector_store", reasoning="factual question")
    assert r.destination == "vector_store"
    print("[PASS] QueryRoute model OK")


def test_web_search_node_sync():
    """Test web_search node logic without event loop (sync wrapper)."""
    import asyncio
    from src.nodes.web_search import web_search

    state = AgentState(current_query="test query", retrieved_docs=[], search_count=0, is_relevant=False)
    result = asyncio.run(web_search(state))
    assert result["search_count"] == 1
    assert len(result["retrieved_docs"]) > 0
    assert result["is_relevant"] is True
    print("[PASS] web_search node OK")


def test_chains_importable():
    from src.chains.router import route_query, QueryRoute
    from src.chains.doc_grader import grade_document, DocGrade
    from src.chains.hallucination_grader import grade_hallucination, HallucinationGrade
    print("[PASS] All chains importable OK")


def test_nodes_importable():
    from src.nodes.retrieve import retrieve
    from src.nodes.grade_documents import grade_documents
    from src.nodes.web_search import web_search
    from src.nodes.generate import generate
    print("[PASS] All nodes importable OK")


def test_settings_loadable():
    from src.config.settings import Settings
    s = Settings(OPENAI_API_KEY="test-key")
    assert s.OPENAI_API_KEY == "test-key"
    assert s.LLM_MODEL == "gpt-4o-mini"
    assert s.TOP_K == 4
    print("[PASS] Settings loadable OK")


if __name__ == "__main__":
    tests = [
        test_agent_state_defaults,
        test_agent_state_mutation,
        test_hallucination_report_valid,
        test_hallucination_report_boundaries,
        test_doc_grade_model,
        test_query_route_model,
        test_web_search_node_sync,
        test_chains_importable,
        test_nodes_importable,
        test_settings_loadable,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"[FAIL] {t.__name__}: {e}")
            failed += 1

    print(f"\n{'='*40}")
    print(f"Results: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)
    print("All tests passed!")
