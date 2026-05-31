"""Mock LLM layer for local demo — returns deterministic responses without API calls."""
from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel

from src.chains.router import QueryRoute
from src.chains.doc_grader import DocGrade
from src.chains.hallucination_grader import HallucinationGrade


class MockChatModel(BaseChatModel):
    """A deterministic mock chat model for testing the graph without API keys."""

    model_name: str = "mock-gpt"
    _response_map: dict[str, str] = {}

    @property
    def _llm_type(self) -> str:
        return "mock-chat"

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None, **kwargs: Any):
        from langchain_core.outputs import ChatGeneration, LLMResult
        combined = " ".join(m.content for m in messages if hasattr(m, "content"))
        resp = self._pick_response(combined, kwargs)
        return LLMResult(generations=[[ChatGeneration(message=AIMessage(content=resp))]])

    def _pick_response(self, prompt: str, kwargs: dict) -> str:
        prompt_lower = prompt.lower()

        # Router response
        if "query classifier" in prompt_lower or "classify the user" in prompt_lower:
            if any(w in prompt_lower for w in ["hello", "hi", "hey", "thanks", "你好"]):
                return '{"destination": "noise", "reasoning": "casual greeting"}'
            if any(w in prompt_lower for w in ["latest", "2026", "recent news", "today", "quantum computing", "ibm"]):
                return '{"destination": "web_search", "reasoning": "time-sensitive / external knowledge needed"}'
            return '{"destination": "vector_store", "reasoning": "factual knowledge question"}'

        # Doc grader response
        if "document relevance grader" in prompt_lower:
            if "rag" in prompt_lower and ("retrieval" in prompt_lower or "augmented" in prompt_lower):
                return '{"is_relevant": true, "reasoning": "document matches RAG topic"}'
            return '{"is_relevant": false, "reasoning": "document not relevant to query"}'

        # Hallucination grader response
        if "hallucination detector" in prompt_lower:
            if "quantum" in prompt_lower or "ibm" in prompt_lower:
                return '{"score": 0.7, "ungrounded_claims": ["IBM 10000-qubit processor claim is unverified"], "verdict": "NOT_SUPPORTED"}'
            return '{"score": 0.1, "ungrounded_claims": [], "verdict": "SUPPORTED"}'

        # Rewrite response
        if "query rewriter" in prompt_lower:
            return "What are the verified, peer-reviewed milestones in quantum computing research published in 2025-2026?"

        # Default generation
        if "rag" in prompt_lower or "retrieval-augmented" in prompt_lower:
            return ("Retrieval-Augmented Generation (RAG) is a technique that enhances large language models "
                    "by retrieving relevant documents from an external knowledge base before generating a response. "
                    "This grounds the model's output in factual, up-to-date information.")
        return ("Based on the provided context, I can offer what information is available. "
                "The source documents do not contain sufficient evidence to fully verify this claim.")


class MockStructuredChain:
    """Wraps MockChatModel to emulate .with_structured_output() for Pydantic models."""

    def __init__(self, response_model: type[BaseModel]):
        self.llm = MockChatModel()
        self.response_model = response_model

    async def ainvoke(self, input_data: dict, **kwargs) -> Any:
        from langchain_core.messages import HumanMessage, SystemMessage
        messages = []
        for k, v in input_data.items():
            if isinstance(v, str):
                messages.append(HumanMessage(content=f"{k}: {v}"))
        raw = self.llm._generate([SystemMessage(content="mock")] + messages)
        text = raw.generations[0][0].message.content
        return self.response_model.model_validate_json(text)


def mock_route_query(query: str) -> QueryRoute:
    llm = MockChatModel()
    from langchain_core.messages import SystemMessage, HumanMessage
    prompt = ("You are a query classifier for an Adaptive RAG system.\n"
              "Classify the user's query into exactly one of: noise, vector_store, web_search.\n"
              "Return JSON with 'destination' and 'reasoning' fields.")
    raw = llm._generate([SystemMessage(content=prompt), HumanMessage(content=f"Query: {query}")])
    import json
    return QueryRoute.model_validate_json(raw.generations[0][0].message.content)


def mock_grade_document(query: str, document: str) -> DocGrade:
    llm = MockChatModel()
    from langchain_core.messages import SystemMessage, HumanMessage
    prompt = ("You are a document relevance grader.\n"
              "Return JSON with 'is_relevant' (bool) and 'reasoning' (string) fields.")
    raw = llm._generate([SystemMessage(content=prompt), HumanMessage(content=f"Query: {query}\nDocument: {document}")])
    return DocGrade.model_validate_json(raw.generations[0][0].message.content)


def mock_hallucination_grade(documents: str, answer: str) -> HallucinationGrade:
    llm = MockChatModel()
    from langchain_core.messages import SystemMessage, HumanMessage
    prompt = ("You are a hallucination detector.\n"
              "Return JSON with 'score' (float 0-1), 'ungrounded_claims' (list), and 'verdict' (SUPPORTED/NOT_SUPPORTED).")
    raw = llm._generate([SystemMessage(content=prompt),
                          HumanMessage(content=f"Documents: {documents}\nAnswer: {answer}")])
    return HallucinationGrade.model_validate_json(raw.generations[0][0].message.content)
