"""Adaptive RAG graph topology — full orchestration with conditional routing."""
from __future__ import annotations

import os
from typing import Literal

from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.prompts import ChatPromptTemplate

from src.state import AgentState
from src.config.settings import get_settings

# ─── Detect mock mode ──────────────────────────────────────────────────────

_USE_MOCK = os.environ.get("OPENAI_API_KEY", "") in ("", "sk-your-key-here")

if _USE_MOCK:
    from src.mock_llm import (
        MockChatModel,
        mock_route_query,
        mock_grade_document,
        mock_hallucination_grade,
    )
else:
    from src.chains.router import route_query
    from src.chains.hallucination_grader import grade_hallucination
    from src.nodes.grade_documents import grade_documents as _real_grade_documents

# ─── LLM factory ───────────────────────────────────────────────────────────


def _make_llm(temperature: float = 0):
    """Create the right ChatModel based on LLM_PROVIDER setting."""
    settings = get_settings()
    if settings.LLM_PROVIDER == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=settings.LLM_MODEL,
            api_key=settings.ANTHROPIC_API_KEY,
            base_url=settings.ANTHROPIC_BASE_URL,
            temperature=temperature,
            max_tokens=1024,
        )
    else:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_API_BASE,
            temperature=temperature,
        )


# ─── Rewrite node ──────────────────────────────────────────────────────────

REWRITE_SYSTEM_PROMPT = """\
You are a query rewriter for an RAG system.
The previous answer contained hallucinations or was not grounded in the source documents.
Rewrite the original query to be more specific, precise, and fact-oriented so that
retrieval can find better supporting documents. Output ONLY the rewritten query, nothing else."""


async def rewrite_query(state: AgentState) -> dict:
    if _USE_MOCK:
        llm = MockChatModel()
        from langchain_core.messages import SystemMessage, HumanMessage
        raw = llm._generate([SystemMessage(content="You are a query rewriter."),
                              HumanMessage(content=f"Original: {state.current_query}")])
        return {"current_query": raw.generations[0][0].message.content.strip()}

    llm = _make_llm()
    prompt = ChatPromptTemplate.from_messages([
        ("system", REWRITE_SYSTEM_PROMPT),
        ("human", "Original query: {query}\n\nHallucination report: {report}"),
    ])
    chain = prompt | llm
    result = await chain.ainvoke({
        "query": state.current_query,
        "report": str(state.hallucination_report.model_dump() if state.hallucination_report else {}),
    })
    return {"current_query": result.content.strip()}


# ─── Router node ───────────────────────────────────────────────────────────

async def route_node(state: AgentState) -> dict:
    if _USE_MOCK:
        route = mock_route_query(state.current_query)
    else:
        route = await route_query(state.current_query)
    return {"route_destination": route.destination}


# ─── Conditional edge functions ────────────────────────────────────────────

def _initial_route(state: AgentState) -> Literal["noise", "vector_store", "web_search"]:
    return state.route_destination  # type: ignore[return-value]


def _grade_route(state: AgentState) -> Literal["generate", "web_search"]:
    if state.is_relevant:
        return "generate"
    if state.search_count < 2:
        return "web_search"
    return "generate"


def _hallucination_route(state: AgentState) -> Literal["end", "rewrite"]:
    if state.hallucination_report and state.hallucination_report.verdict == "SUPPORTED":
        return "end"
    if state.search_count < 2:
        return "rewrite"
    return "end"


# ─── Noise handler ─────────────────────────────────────────────────────────

async def noise_reply(state: AgentState) -> dict:
    if _USE_MOCK:
        llm = MockChatModel()
        from langchain_core.messages import HumanMessage
        raw = llm._generate([HumanMessage(content=state.current_query)])
        return {"answer": raw.generations[0][0].message.content}

    llm = _make_llm(temperature=0.3)
    result = await llm.ainvoke(state.current_query)
    return {"answer": result.content}


# ─── Hallucination grading node ────────────────────────────────────────────

async def hallucination_grade_node(state: AgentState) -> dict:
    docs_text = "\n---\n".join(d.page_content for d in state.retrieved_docs)

    if _USE_MOCK:
        grade = mock_hallucination_grade(documents=docs_text, answer=state.answer)
        from src.state import HallucinationReport
        report = HallucinationReport(
            score=grade.score,
            ungrounded_claims=grade.ungrounded_claims,
            verdict=grade.verdict,  # type: ignore[arg-type]
        )
    else:
        report = await grade_hallucination(documents=docs_text, answer=state.answer)

    return {"hallucination_report": report}


# ─── Grade documents node ──────────────────────────────────────────────────

async def grade_documents_node(state: AgentState) -> dict:
    if _USE_MOCK:
        relevant_docs = []
        for doc in state.retrieved_docs:
            result = mock_grade_document(query=state.current_query, document=doc.page_content)
            if result.is_relevant:
                relevant_docs.append(doc)
        return {"retrieved_docs": relevant_docs, "is_relevant": len(relevant_docs) > 0}

    return await _real_grade_documents(state)


# ─── Generate node ─────────────────────────────────────────────────────────

async def generate_node(state: AgentState) -> dict:
    if _USE_MOCK:
        llm = MockChatModel()
        context = "\n---\n".join(d.page_content for d in state.retrieved_docs)
        from langchain_core.messages import SystemMessage, HumanMessage
        raw = llm._generate([
            SystemMessage(content="Answer based on context."),
            HumanMessage(content=f"Context:\n{context}\n\nQuestion: {state.current_query}"),
        ])
        return {"answer": raw.generations[0][0].message.content}

    llm = _make_llm()
    from langchain_core.output_parsers import StrOutputParser
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a helpful assistant. Answer based on the provided context."),
        ("human", "Context:\n{context}\n\nQuestion: {question}"),
    ])
    chain = prompt | llm | StrOutputParser()
    context = "\n---\n".join(d.page_content for d in state.retrieved_docs)
    answer = await chain.ainvoke({"context": context, "question": state.current_query})
    return {"answer": answer}


# ─── Graph builder ─────────────────────────────────────────────────────────

from src.nodes.retrieve import retrieve
from src.nodes.web_search import web_search


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("route", route_node)
    graph.add_node("noise_reply", noise_reply)
    graph.add_node("retrieve", retrieve)
    graph.add_node("grade_documents", grade_documents_node)
    graph.add_node("web_search", web_search)
    graph.add_node("generate", generate_node)
    graph.add_node("hallucination_grade", hallucination_grade_node)
    graph.add_node("rewrite_query", rewrite_query)

    graph.add_edge(START, "route")

    graph.add_conditional_edges(
        "route", _initial_route,
        {"noise": "noise_reply", "vector_store": "retrieve", "web_search": "web_search"},
    )
    graph.add_edge("noise_reply", END)
    graph.add_edge("retrieve", "grade_documents")
    graph.add_conditional_edges(
        "grade_documents", _grade_route,
        {"generate": "generate", "web_search": "web_search"},
    )
    graph.add_edge("web_search", "generate")
    graph.add_edge("generate", "hallucination_grade")
    graph.add_conditional_edges(
        "hallucination_grade", _hallucination_route,
        {"end": END, "rewrite": "rewrite_query"},
    )
    graph.add_edge("rewrite_query", "retrieve")

    return graph


def compile_graph():
    graph = build_graph()
    memory = MemorySaver()
    return graph.compile(checkpointer=memory)
