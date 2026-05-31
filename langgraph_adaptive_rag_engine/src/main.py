"""Adaptive RAG — main entry point with two integration test cases."""
from __future__ import annotations

import asyncio
import json
from dotenv import load_dotenv
from src.graph import compile_graph


async def run_case(graph, config: dict, case_label: str, query: str):
    """Run a single query through the graph and stream node events."""
    print(f"\n{'='*60}")
    print(f"  CASE {case_label}  |  Query: {query}")
    print(f"{'='*60}\n")

    inputs = {"current_query": query}

    async for event in graph.astream(inputs, config=config, stream_mode="updates"):
        for node_name, node_output in event.items():
            # Truncate long fields for readability
            display = {}
            for k, v in (node_output if isinstance(node_output, dict) else {}).items():
                if k == "retrieved_docs":
                    display[k] = f"[{len(v)} docs]"
                elif k == "messages":
                    display[k] = f"[{len(v)} msgs]"
                elif k == "hallucination_report" and v is not None:
                    display[k] = {
                        "score": v.score if hasattr(v, "score") else v.get("score"),
                        "verdict": v.verdict if hasattr(v, "verdict") else v.get("verdict"),
                    }
                elif isinstance(v, str) and len(v) > 200:
                    display[k] = v[:200] + "..."
                else:
                    display[k] = v
            print(f"  [{node_name}]")
            print(f"    {json.dumps(display, default=str, ensure_ascii=False, indent=4)}")
            print()

    # Final state snapshot
    state_snapshot = await graph.aget_state(config)
    answer = state_snapshot.values.get("answer", "")
    print(f"  FINAL ANSWER:\n    {answer}\n")
    print(f"  search_count = {state_snapshot.values.get('search_count', 0)}")
    print(f"  is_relevant  = {state_snapshot.values.get('is_relevant', False)}")
    hr = state_snapshot.values.get("hallucination_report")
    if hr:
        verdict = hr.verdict if hasattr(hr, "verdict") else hr.get("verdict")
        score = hr.score if hasattr(hr, "score") else hr.get("score")
        print(f"  hallucination: score={score}, verdict={verdict}")
    print()


async def main():
    load_dotenv()

    graph = compile_graph()

    # ── Case A: local knowledge-base hit ────────────────────────
    # In demo mode (no Qdrant running), retrieve returns empty
    # and the system auto-falls through to web_search → generate.
    # In production with Qdrant populated, this would hit vector_store.
    config_a = {"configurable": {"thread_id": "interview_demo_001"}}
    await run_case(graph, config_a, "A", "What is Retrieval-Augmented Generation (RAG)?")

    # ── Case B: web_search + hallucination reflection ───────────
    config_b = {"configurable": {"thread_id": "interview_demo_002"}}
    await run_case(graph, config_b, "B",
        "What are the latest developments in quantum computing as of 2026? "
        "I heard that IBM just released a 10,000-qubit processor — is that true?")


if __name__ == "__main__":
    asyncio.run(main())
