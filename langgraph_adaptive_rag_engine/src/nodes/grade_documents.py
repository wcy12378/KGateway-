from __future__ import annotations

import asyncio
import logging

from src.chains.doc_grader import grade_document
from src.state import AgentState

logger = logging.getLogger(__name__)


async def grade_documents(state: AgentState) -> dict:
    """Grade each retrieved document for relevance to the query.

    Uses ``asyncio.gather`` to parallelise relevance scoring across all
    retrieved document chunks simultaneously, reducing wall-clock latency
    from O(n × LLM_latency) to O(LLM_latency).

    Filters out irrelevant documents. Sets is_relevant=False if no
    documents pass the relevance check.
    """
    async def _grade_one(doc):
        return doc, await grade_document(
            query=state.current_query,
            document=doc.page_content,
        )

    results = await asyncio.gather(
        *[_grade_one(doc) for doc in state.retrieved_docs],
        return_exceptions=True,
    )

    relevant_docs = []
    for result in results:
        if isinstance(result, Exception):
            logger.warning("Document grading failed: %s", result)
            continue
        doc, grade = result
        if grade.is_relevant:
            relevant_docs.append(doc)

    return {
        "retrieved_docs": relevant_docs,
        "is_relevant": len(relevant_docs) > 0,
    }
