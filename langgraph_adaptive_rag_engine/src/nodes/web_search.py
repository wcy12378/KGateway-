from __future__ import annotations

import asyncio
import hashlib
from typing import Any

from langchain_core.documents import Document

from src.state import AgentState

# ---------------------------------------------------------------------------
# Placeholder search adapter — replace with real Tavily / SerpAPI / Bing.
# ---------------------------------------------------------------------------


async def _simulate_web_search(query: str, num_results: int = 3) -> list[dict[str, Any]]:
    """Simulate a web search with a small async delay.

    Returns a list of dicts with 'title', 'snippet', and 'url' keys.
    """
    await asyncio.sleep(0.1)  # simulate network latency

    results = []
    for i in range(num_results):
        uid = hashlib.md5(f"{query}_{i}".encode()).hexdigest()[:8]
        results.append({
            "title": f"Result {i + 1} for: {query}",
            "snippet": f"This is simulated web content about '{query}' from result {i + 1}. "
                       f"It provides additional context that may not be in the internal knowledge base.",
            "url": f"https://example.com/{uid}",
        })
    return results


async def web_search(state: AgentState) -> dict:
    """Fetch external search results and append to retrieved_docs.

    When the knowledge base has no relevant docs (is_relevant == False),
    this node fills the gap with web results and bumps search_count.
    """
    raw_results = await _simulate_web_search(state.current_query)

    new_docs = [
        Document(
            page_content=f"{r['title']}: {r['snippet']}",
            metadata={"source": "web_search", "url": r["url"]},
        )
        for r in raw_results
    ]

    return {
        "retrieved_docs": list(state.retrieved_docs) + new_docs,
        "search_count": state.search_count + 1,
        "is_relevant": True,
    }
