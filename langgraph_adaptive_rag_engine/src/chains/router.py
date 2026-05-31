from __future__ import annotations

from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field


class QueryRoute(BaseModel):
    destination: Literal["noise", "vector_store", "web_search"] = Field(
        ..., description="Route the query: 'noise' for small talk, 'vector_store' for knowledge-base retrieval, 'web_search' for internet search",
    )
    reasoning: str = Field(default="", description="One-line explanation")


ROUTER_SYSTEM_PROMPT = """\
You are a query classifier for an Adaptive RAG system.

Classify the user's query into exactly one of:
- **noise**: Casual greetings, small talk, off-topic chatter, or questions that do not require any knowledge retrieval.
- **vector_store**: Factual, domain-specific questions that can be answered by searching an internal document knowledge base.
- **web_search**: Questions that require up-to-date, real-world, or time-sensitive information not likely in a static document store.

You MUST return a JSON object with "destination" and "reasoning" fields. No other output."""


def _build_chain():
    from src.graph import _make_llm
    llm = _make_llm()
    structured_llm = llm.with_structured_output(QueryRoute)
    prompt = ChatPromptTemplate.from_messages([
        ("system", ROUTER_SYSTEM_PROMPT),
        ("human", "Query: {query}"),
    ])
    return prompt | structured_llm


async def route_query(query: str) -> QueryRoute:
    chain = _build_chain()
    return await chain.ainvoke({"query": query})
