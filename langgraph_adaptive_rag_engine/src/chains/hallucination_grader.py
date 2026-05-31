from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from src.state import HallucinationReport


class HallucinationGrade(BaseModel):
    score: float = Field(..., ge=0.0, le=1.0, description="0.0 = fully grounded, 1.0 = pure hallucination")
    ungrounded_claims: list[str] = Field(default_factory=list, description="Claims not supported by documents")
    verdict: str = Field(..., description="'SUPPORTED' or 'NOT_SUPPORTED'")


HALLUCINATION_SYSTEM_PROMPT = """\
You are a strict hallucination detector for an RAG system.

Given a list of source documents and a generated answer, evaluate whether the answer is fully grounded in the documents.

For each claim in the answer, check if it has explicit support in the provided documents.
- If ALL claims are supported: score=0.0, verdict="SUPPORTED"
- If SOME claims lack support: score>0.0, list the unsupported claims in ungrounded_claims, verdict="NOT_SUPPORTED"
- If the answer contradicts or fabricates information not in the documents: score approaches 1.0, verdict="NOT_SUPPORTED"

You MUST return a JSON object with "score", "ungrounded_claims", and "verdict" fields. No other output."""


def _build_chain():
    from src.graph import _make_llm
    llm = _make_llm()
    structured_llm = llm.with_structured_output(HallucinationGrade)
    prompt = ChatPromptTemplate.from_messages([
        ("system", HALLUCINATION_SYSTEM_PROMPT),
        ("human", "Documents:\n{documents}\n\nAnswer: {answer}"),
    ])
    return prompt | structured_llm


async def grade_hallucination(documents: str, answer: str) -> HallucinationReport:
    chain = _build_chain()
    result = await chain.ainvoke({"documents": documents, "answer": answer})
    return HallucinationReport(
        score=result.score,
        ungrounded_claims=result.ungrounded_claims,
        verdict=result.verdict,  # type: ignore[arg-type]
    )
