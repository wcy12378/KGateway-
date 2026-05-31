from __future__ import annotations

import requests
from langchain_core.documents import Document

from src.config.settings import get_settings
from src.state import AgentState


async def retrieve(state: AgentState) -> dict:
    """Retrieve documents from Qdrant via REST API."""
    settings = get_settings()

    try:
        # Qdrant scroll endpoint — fetch all points, then rank by simple text match
        # (real deployments would use vector similarity search via embeddings)
        r = requests.post(
            f"{settings.QDRANT_URL}/collections/{settings.QDRANT_COLLECTION}/points/scroll",
            json={"limit": 100, "with_payload": True, "with_vectors": False},
            timeout=5,
        )
        r.raise_for_status()
        data = r.json()

        docs = []
        query_lower = state.current_query.lower()
        matched = []
        for point in data.get("result", {}).get("points", []):
            payload = point.get("payload", {})
            content = payload.get("page_content", "")
            doc = Document(page_content=content, metadata=payload.get("metadata", {}))
            # Keyword match or include all if no match (demo fallback)
            if any(kw in content.lower() for kw in query_lower.split()):
                matched.append(doc)
            docs.append(doc)

        # Use matched docs; if none matched, return all (demo fallback for cross-language)
        result_docs = matched if matched else docs
        result_docs = result_docs[: settings.TOP_K]
    except Exception:
        result_docs = []

    return {"retrieved_docs": result_docs}
