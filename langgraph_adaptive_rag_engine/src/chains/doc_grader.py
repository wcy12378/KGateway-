from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field


class DocGrade(BaseModel):
    is_relevant: bool = Field(..., description="True if the document is relevant to the query")
    reasoning: str = Field(default="", description="One-line explanation")


DOC_GRADER_SYSTEM_PROMPT = """\
You are a document relevance grader for an RAG system.

Given a user query and a document chunk, determine whether the document is relevant to answering the query.

You MUST return a JSON object with "is_relevant" (boolean) and "reasoning" (string) fields. No other output."""


def _build_chain():
    from src.graph import _make_llm
    llm = _make_llm()
    structured_llm = llm.with_structured_output(DocGrade)
    prompt = ChatPromptTemplate.from_messages([
        ("system", DOC_GRADER_SYSTEM_PROMPT),
        ("human", "Query: {query}\n\nDocument: {document}"),
    ])
    return prompt | structured_llm


async def grade_document(query: str, document: str) -> DocGrade:
    chain = _build_chain()
    return await chain.ainvoke({"query": query, "document": document})
