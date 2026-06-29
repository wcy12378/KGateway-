"""HTTP 适配层路由。

本模块负责 FastAPI 路由、请求接收、响应封装和监控接口输出。业务编排由
`ChatOrchestrator` 完成，本文件不直接实现缓存、检索、Agent 或 LLM 流程。
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from src.agents.runtime import AgentRuntime
from src.application.orchestrator import ChatOrchestrator
from src.application.rag_service import HybridRagService
from src.application.stream_contract import PROTOCOL_VERSION, contract_payload, error_frame, sse_done
from src.config import config
from src.core.cache import SemanticCacheManager
from src.core.observability import observer
from src.core.protection import CircuitBreaker
from src.core.reranker import Reranker
from src.core.router import ModelRouter
from src.core.schemas import Department, GatewayRequest
from src.core.tools.builtin import configure_knowledge_query
from src.db.bm25_client import SparseRetriever
from src.db.qdrant_client import QdrantVectorStore

logger = logging.getLogger("kagent.api.routes")

router = APIRouter(prefix="/api/v1/gateway", tags=["streaming"])
monitor_router = APIRouter(prefix="/api/v1/monitor", tags=["monitoring"])
STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
    "X-KAgent-Contract-Version": PROTOCOL_VERSION,
}

_model_router: ModelRouter | None = None
_bm25_retriever: SparseRetriever | None = None
_reranker: Reranker | None = None
_agent_runtime: AgentRuntime | None = None
_semantic_cache: SemanticCacheManager | None = None
_circuit_breaker: CircuitBreaker | None = None
_rag_service: HybridRagService | None = None
_chat_orchestrator: ChatOrchestrator | None = None


def init_router(
    model_router: ModelRouter,
    bm25_retriever: Optional[SparseRetriever] = None,
    reranker: Optional[Reranker] = None,
    agent_runtime: Optional[AgentRuntime] = None,
    semantic_cache: Optional[SemanticCacheManager] = None,
    circuit_breaker: Optional[CircuitBreaker] = None,
    qdrant_store: Optional[QdrantVectorStore] = None,
) -> None:
    """Wire runtime dependencies once at startup."""
    global _model_router, _bm25_retriever, _reranker, _agent_runtime, _semantic_cache, _circuit_breaker, _rag_service, _chat_orchestrator
    _model_router = model_router
    _bm25_retriever = bm25_retriever
    _reranker = reranker
    _agent_runtime = agent_runtime
    _semantic_cache = semantic_cache
    _circuit_breaker = circuit_breaker

    _rag_service = HybridRagService(
        bm25_retriever=bm25_retriever,
        reranker=reranker,
        qdrant_store=qdrant_store,
    )
    configure_knowledge_query(_rag_service.retrieve)
    if _agent_runtime is not None:
        _agent_runtime._rag_pipeline_fn = _rag_service.retrieve

    _chat_orchestrator = ChatOrchestrator(
        model_router=model_router,
        agent_runtime=agent_runtime,
        semantic_cache=semantic_cache,
        circuit_breaker=circuit_breaker,
        observer=observer,
    )


def _normalize_latency_distribution(raw: Dict[str, Any]) -> Dict[str, int]:
    return {
        "under_100ms": int(raw.get("under_100ms", raw.get("<100ms", 0)) or 0),
        "100_500ms": int(raw.get("100_500ms", raw.get("100-500ms", 0)) or 0),
        "500ms_1s": int(raw.get("500ms_1s", raw.get("500ms-1s", 0)) or 0),
        "1s_5s": int(raw.get("1s_5s", raw.get("1-5s", 0)) or 0),
        "over_5s": int(raw.get("over_5s", raw.get(">5s", 0)) or 0),
    }


def _normalize_span_list(spans: Any) -> List[Dict[str, Any]]:
    if isinstance(spans, list):
        return [
            {
                "name": str(span.get("name", "")),
                "duration_ms": float(span.get("duration_ms", 0.0) or 0.0),
                "result": span.get("result") if isinstance(span.get("result"), str) else span.get("status"),
            }
            for span in spans
            if isinstance(span, dict)
        ]

    if isinstance(spans, dict):
        return [
            {
                "name": name,
                "duration_ms": float(info.get("duration_ms", 0.0) or 0.0),
                "result": info.get("result") if isinstance(info.get("result"), str) else info.get("status"),
            }
            for name, info in spans.items()
            if isinstance(info, dict)
        ]

    return []


def _normalize_trace_record(trace: Dict[str, Any]) -> Dict[str, Any]:
    trace_id = str(trace.get("trace_id", ""))
    timestamp = (
        trace.get("timestamp")
        or trace.get("created_at")
        or time.strftime("%Y-%m-%dT%H:%M:%S%z")
    )
    model = str(trace.get("model") or trace.get("model_used") or "unknown")
    routing = str(trace.get("routing_decision") or model)
    department = str(trace.get("department") or "general")
    return {
        "trace_id": trace_id,
        "timestamp": timestamp,
        "cache_hit": bool(trace.get("cache_hit", False)),
        "model": model,
        "total_tokens": int(trace.get("total_tokens", 0) or 0),
        "estimated_cost_usd": float(trace.get("estimated_cost_usd", 0.0) or 0.0),
        "ttft_ms": float(trace.get("ttft_ms", 0.0) or 0.0),
        "total_latency_ms": float(trace.get("total_latency_ms", 0.0) or 0.0),
        "circuit_breaker": bool(trace.get("circuit_breaker", False)),
        "routing_decision": routing,
        "agent_iterations": int(trace.get("agent_iterations", 0) or 0),
        "user_id": str(trace.get("user_id", "unknown")),
        "department": department,
        "spans": _normalize_span_list(trace.get("spans", {})),
    }


def build_metrics_payload() -> Dict[str, Any]:
    metrics = observer.metrics.snapshot()
    return {
        "total_requests": int(metrics.get("total_requests", 0) or 0),
        "cache_hit_rate": float(metrics.get("cache_hit_rate", 0.0) or 0.0),
        "cache_hits": int(metrics.get("cache_hits", 0) or 0),
        "cache_misses": int(metrics.get("cache_misses", 0) or 0),
        "total_tokens": int(metrics.get("total_tokens", 0) or 0),
        "total_cost_usd": float(metrics.get("total_cost_usd", 0.0) or 0.0),
        "avg_latency_ms": float(metrics.get("avg_latency_ms", 0.0) or 0.0),
        "latency_distribution": _normalize_latency_distribution(metrics.get("latency_distribution", {})),
    }


def build_trace_list_payload(limit: int = 100, offset: int = 0) -> Dict[str, Any]:
    traces = list(reversed(observer.metrics.recent_traces))
    total = len(traces)
    safe_limit = max(0, limit)
    safe_offset = max(0, offset)
    page = traces[safe_offset : safe_offset + safe_limit] if safe_offset < total else []
    return {
        "total": total,
        "limit": safe_limit,
        "offset": safe_offset,
        "traces": [_normalize_trace_record(trace) for trace in page],
    }


def build_circuit_breaker_payload() -> Dict[str, Any]:
    if _circuit_breaker is None:
        return {
            "name": "llm_api",
            "state": "CLOSED",
            "failure_count": 0,
            "failure_threshold": config.circuit_breaker_threshold,
            "recovery_timeout": config.circuit_breaker_timeout,
            "total_requests": 0,
            "total_failures": 0,
            "total_rejected": 0,
        }
    return _circuit_breaker.stats()


@monitor_router.get("/metrics")
async def monitor_metrics() -> Dict[str, Any]:
    return build_metrics_payload()


@monitor_router.get("/traces")
async def monitor_traces(limit: int = 100, offset: int = 0) -> Dict[str, Any]:
    return build_trace_list_payload(limit=limit, offset=offset)


@monitor_router.get("/circuit-breaker")
async def monitor_circuit_breaker() -> Dict[str, Any]:
    return build_circuit_breaker_payload()


@monitor_router.post("/circuit-breaker/force-open")
async def monitor_circuit_breaker_force_open() -> Dict[str, Any]:
    if _circuit_breaker is not None:
        _circuit_breaker.force_open()
    return build_circuit_breaker_payload()


@monitor_router.post("/circuit-breaker/force-close")
async def monitor_circuit_breaker_force_close() -> Dict[str, Any]:
    if _circuit_breaker is not None:
        _circuit_breaker.force_close()
    return build_circuit_breaker_payload()


async def _error_stream(message: str):
    yield error_frame(message)
    yield sse_done()


@router.get("/contract", summary="Gateway stream contract")
async def gateway_contract() -> Dict[str, Any]:
    return contract_payload()


@router.post("/stream", summary="SSE streaming gateway")
async def gateway_stream(
    body: GatewayRequest,
    request: Request,
) -> StreamingResponse:
    auth_user = getattr(request.state, "user", None)
    if auth_user is not None:
        body.user_id = auth_user.user_id
        body.tenant_id = auth_user.tenant_id
        try:
            body.department = Department(auth_user.department)
        except ValueError:
            body.department = Department.GENERAL

    logger.info(
        "stream request: user=%s tenant=%s dept=%s adv=%s q_len=%d",
        body.user_id,
        body.tenant_id,
        body.department.value,
        body.advanced_reasoning,
        len(body.question),
    )

    if _chat_orchestrator is None:
        return StreamingResponse(
            _error_stream("网关未初始化"),
            media_type="text/event-stream",
            headers=STREAM_HEADERS,
        )

    return StreamingResponse(
        _chat_orchestrator.stream(body, request),
        media_type="text/event-stream",
        headers=STREAM_HEADERS,
    )
