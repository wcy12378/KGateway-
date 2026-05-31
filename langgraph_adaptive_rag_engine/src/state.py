from __future__ import annotations

from typing import Any, Literal, Optional

from langchain_core.documents import Document
from pydantic import BaseModel, Field


class HallucinationReport(BaseModel):
    """Structured output for hallucination detection."""

    score: float = Field(..., ge=0.0, le=1.0, description="0=no hallucination, 1=pure hallucination")
    ungrounded_claims: list[str] = Field(default_factory=list)
    verdict: Literal["SUPPORTED", "NOT_SUPPORTED"]


class AgentState(BaseModel):
    """Type-safe state machine for the Adaptive RAG graph.

    The state is passed node-to-node; every mutation flows through
    the LangGraph reducer pattern so parallel branches compose correctly.
    """

    # ── Core fields ──────────────────────────────────────────────
    messages: list[dict[str, Any]] = Field(default_factory=list)
    current_query: str = Field(default="")
    retrieved_docs: list[Document] = Field(default_factory=list)

    # ── Routing / decision flags ─────────────────────────────────
    route_destination: str = Field(default="", description="Output of the initial router node")
    search_count: int = Field(default=0, description="Number of retrieval iterations so far")
    is_relevant: bool = Field(default=False, description="Whether query is relevant to the knowledge base")

    # ── Hallucination tracking ───────────────────────────────────
    hallucination_report: Optional[HallucinationReport] = None

    # ── Final output ─────────────────────────────────────────────
    answer: str = Field(default="")
