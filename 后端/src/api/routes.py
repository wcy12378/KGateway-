"""HTTP 适配层路由。

本模块负责 FastAPI 路由、请求接收、响应封装和监控接口输出。业务编排由
`ChatOrchestrator` 完成，本文件不直接实现缓存、检索、Agent 或 LLM 流程。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from src.agents.runtime import AgentRuntime
from src.application.orchestrator import ChatOrchestrator
from src.application.rag_service import HybridRagService
from src.application.stream_contract import PROTOCOL_VERSION, contract_payload, error_frame, sse_done
from src.config import config
from src.core.cache import SemanticCacheManager
from src.core.agent.workflow import WorkflowEngine, WorkflowNotFoundError
from src.core.observability import observer
from src.core.protection import CircuitBreaker
from src.core.prompts.registry import PromptNotFoundError, PromptRegistry
from src.core.reranker import Reranker
from src.core.router import ModelRouter
from src.core.schemas import (
    Department,
    GatewayRequest,
    GatewayWorkflowRequest,
    GatewayWorkflowResponse,
    WorkflowStepResponse,
)
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

def init_router(
    model_router: ModelRouter,
    bm25_retriever: Optional[SparseRetriever] = None,
    reranker: Optional[Reranker] = None,
    agent_runtime: Optional[AgentRuntime] = None,
    semantic_cache: Optional[SemanticCacheManager] = None,
    circuit_breaker: Optional[CircuitBreaker] = None,
    qdrant_store: Optional[QdrantVectorStore] = None,
    workflow_engine: Optional[WorkflowEngine] = None,
    prompt_registry: Optional[PromptRegistry] = None,
    provider_factory: Any = None,
    fast_lane: Any = None,
) -> ChatOrchestrator:
    """Wire runtime dependencies once at startup."""
    rag_service = HybridRagService(
        bm25_retriever=bm25_retriever,
        reranker=reranker,
        qdrant_store=qdrant_store,
    )
    configure_knowledge_query(rag_service.retrieve)
    if agent_runtime is not None:
        agent_runtime._rag_pipeline_fn = rag_service.retrieve

    return ChatOrchestrator(
        model_router=model_router,
        agent_runtime=agent_runtime,
        semantic_cache=semantic_cache,
        circuit_breaker=circuit_breaker,
        observer=observer,
        provider_factory=provider_factory,
        rag_service=rag_service,
        fast_lane=fast_lane,
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


def build_metrics_payload(
    semantic_cache: SemanticCacheManager | None = None,
) -> Dict[str, Any]:
    metrics = observer.metrics.snapshot()
    cache_status = {
        "connected": bool(semantic_cache and semantic_cache.connected),
        "semantic_ready": bool(semantic_cache and getattr(semantic_cache, "semantic_ready", False)),
        "namespace_version": str(getattr(semantic_cache, "namespace_version", "")),
    }
    return {
        "total_requests": int(metrics.get("total_requests", 0) or 0),
        "cache_hit_rate": float(metrics.get("cache_hit_rate", 0.0) or 0.0),
        "cache_hits": int(metrics.get("cache_hits", 0) or 0),
        "cache_misses": int(metrics.get("cache_misses", 0) or 0),
        "exact_cache_hits": int(metrics.get("exact_cache_hits", 0) or 0),
        "semantic_cache_hits": int(metrics.get("semantic_cache_hits", 0) or 0),
        "fast_lane_hits": int(metrics.get("fast_lane_hits", 0) or 0),
        "total_tokens": int(metrics.get("total_tokens", 0) or 0),
        "total_cost_usd": float(metrics.get("total_cost_usd", 0.0) or 0.0),
        "avg_latency_ms": float(metrics.get("avg_latency_ms", 0.0) or 0.0),
        "latency_distribution": _normalize_latency_distribution(metrics.get("latency_distribution", {})),
        "cache": cache_status,
    }


def build_trace_list_payload(
    limit: int = 100,
    offset: int = 0,
    *,
    tenant_id: str | None = None,
    user_id: str | None = None,
) -> Dict[str, Any]:
    traces = list(reversed(observer.metrics.recent_traces))
    if tenant_id is not None:
        traces = [trace for trace in traces if trace.get("tenant_id") == tenant_id]
    if user_id is not None:
        traces = [trace for trace in traces if trace.get("user_id") == user_id]
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


def build_circuit_breaker_payload(
    circuit_breaker: CircuitBreaker | None = None,
) -> Dict[str, Any]:
    if circuit_breaker is None:
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
    return circuit_breaker.stats()


@monitor_router.get("/metrics")
async def monitor_metrics(request: Request) -> Dict[str, Any]:
    return build_metrics_payload(getattr(request.app.state, "semantic_cache", None))


@monitor_router.get("/traces")
async def monitor_traces(request: Request, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
    if getattr(request.state, "auth_method", None) == "api_key":
        return build_trace_list_payload(limit=limit, offset=offset)
    auth_user = getattr(request.state, "user", None)
    if auth_user is None:
        raise HTTPException(status_code=401, detail="缺少认证身份")
    return build_trace_list_payload(
        limit=limit,
        offset=offset,
        tenant_id=auth_user.tenant_id,
        user_id=auth_user.user_id,
    )


@monitor_router.get("/circuit-breaker")
async def monitor_circuit_breaker(request: Request) -> Dict[str, Any]:
    return build_circuit_breaker_payload(getattr(request.app.state, "circuit_breaker", None))


@monitor_router.post("/circuit-breaker/force-open")
async def monitor_circuit_breaker_force_open(request: Request) -> Dict[str, Any]:
    if getattr(request.state, "auth_method", None) != "api_key":
        raise HTTPException(status_code=403, detail="熔断器控制仅允许 API Key 管理调用")
    circuit_breaker = getattr(request.app.state, "circuit_breaker", None)
    if circuit_breaker is not None:
        circuit_breaker.force_open()
    return build_circuit_breaker_payload(circuit_breaker)


@monitor_router.post("/circuit-breaker/force-close")
async def monitor_circuit_breaker_force_close(request: Request) -> Dict[str, Any]:
    if getattr(request.state, "auth_method", None) != "api_key":
        raise HTTPException(status_code=403, detail="熔断器控制仅允许 API Key 管理调用")
    circuit_breaker = getattr(request.app.state, "circuit_breaker", None)
    if circuit_breaker is not None:
        circuit_breaker.force_close()
    return build_circuit_breaker_payload(circuit_breaker)


async def _error_stream(message: str):
    yield error_frame(message)
    yield sse_done()


@router.get("/contract", summary="Gateway stream contract")
async def gateway_contract() -> Dict[str, Any]:
    return contract_payload()


def _apply_authenticated_identity(body: GatewayRequest, request: Request) -> None:
    auth_user = getattr(request.state, "user", None)
    if auth_user is None:
        return
    body.user_id = auth_user.user_id
    body.tenant_id = auth_user.tenant_id
    try:
        body.department = Department(auth_user.department)
    except ValueError:
        body.department = Department.GENERAL


@router.get("/workflows", summary="List multi-agent workflows")
async def gateway_workflows(request: Request) -> Dict[str, Any]:
    workflow_engine = getattr(request.app.state, "workflow_engine", None)
    if workflow_engine is None:
        raise HTTPException(status_code=503, detail="工作流引擎未初始化")
    return {"workflows": workflow_engine.list_workflows()}


@router.get("/prompts", summary="List Prompt templates and versions")
async def gateway_prompts(request: Request) -> Dict[str, Any]:
    prompt_registry = getattr(request.app.state, "prompt_registry", None)
    if prompt_registry is None:
        raise HTTPException(status_code=503, detail="Prompt 注册表未初始化")
    return {"prompts": prompt_registry.list()}


@router.post(
    "/prompts/{name}/versions/{version}/activate",
    summary="Activate a Prompt version",
)
async def gateway_prompt_activate(
    name: str,
    version: str,
    request: Request,
) -> Dict[str, Any]:
    prompt_registry = getattr(request.app.state, "prompt_registry", None)
    if prompt_registry is None:
        raise HTTPException(status_code=503, detail="Prompt 注册表未初始化")
    if getattr(request.state, "auth_method", None) != "api_key":
        raise HTTPException(status_code=403, detail="Prompt 切换仅允许 API Key 管理调用")
    try:
        template = prompt_registry.activate(name, version)
    except PromptNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    logger.warning(
        "Prompt 运行时版本切换: name=%s version=%s hash=%s",
        template.name,
        template.version,
        template.content_hash,
    )
    return {
        "name": template.name,
        "active_version": template.version,
        "hash": template.content_hash,
    }


@router.get("/audit", summary="Query tool call audit log")
async def gateway_audit(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    tool: Optional[str] = Query(default=None, min_length=1, max_length=64),
    result_status: Optional[str] = Query(default=None, pattern="^(success|failure)$"),
    trace_id: Optional[str] = Query(default=None, min_length=1, max_length=128),
    tenant_id: Optional[str] = Query(default=None, min_length=1, max_length=128),
    user_id: Optional[str] = Query(default=None, min_length=1, max_length=128),
) -> Dict[str, Any]:
    audit_logger = getattr(request.app.state, "audit_logger", None)
    if audit_logger is None:
        raise HTTPException(status_code=503, detail="审计日志未初始化")
    auth_user = getattr(request.state, "user", None)
    if auth_user is None:
        raise HTTPException(status_code=401, detail="缺少认证身份")

    if getattr(request.state, "auth_method", None) != "api_key":
        tenant_id = auth_user.tenant_id
        user_id = auth_user.user_id

    return audit_logger.query(
        limit=limit,
        offset=offset,
        tenant_id=tenant_id,
        user_id=user_id,
        tool_name=tool,
        result_status=result_status,
        trace_id=trace_id,
    )


@router.post(
    "/workflow",
    response_model=GatewayWorkflowResponse,
    summary="Execute multi-agent workflow",
)
async def gateway_workflow(
    body: GatewayWorkflowRequest,
    request: Request,
) -> GatewayWorkflowResponse:
    workflow_engine = getattr(request.app.state, "workflow_engine", None)
    if workflow_engine is None:
        raise HTTPException(status_code=503, detail="工作流引擎未初始化")
    _apply_authenticated_identity(body, request)
    context = {
        "user_id": body.user_id,
        "tenant_id": body.tenant_id,
        "department": body.department.value,
        "session_id": body.session_id,
    }
    try:
        result = await asyncio.wait_for(
            workflow_engine.run(
                body.workflow_name,
                body.question,
                context=context,
            ),
            timeout=max(float(config.workflow_timeout_seconds), 0.001),
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="工作流执行超时") from exc
    except WorkflowNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return GatewayWorkflowResponse(
        workflow_name=result.workflow_name,
        mode=result.mode.value,
        status=result.status,
        final_answer=result.final_answer,
        session_id=body.session_id,
        steps=[
            WorkflowStepResponse(
                agent_name=step.agent_name,
                status=step.status,
                answer=step.output.answer if step.output else "",
                duration_ms=step.duration_ms,
                total_tokens=step.total_tokens,
                error=step.error,
            )
            for step in result.steps
        ],
        total_duration_ms=result.total_duration_ms,
        total_tokens=result.total_tokens,
    )


@router.post("/stream", summary="SSE streaming gateway")
async def gateway_stream(
    body: GatewayRequest,
    request: Request,
) -> StreamingResponse:
    _apply_authenticated_identity(body, request)

    logger.info(
        "stream request: user=%s tenant=%s dept=%s adv=%s q_len=%d",
        body.user_id,
        body.tenant_id,
        body.department.value,
        body.advanced_reasoning,
        len(body.question),
    )

    chat_orchestrator = getattr(request.app.state, "chat_orchestrator", None)
    if chat_orchestrator is None:
        return StreamingResponse(
            _error_stream("网关未初始化"),
            media_type="text/event-stream",
            headers=STREAM_HEADERS,
        )

    return StreamingResponse(
        chat_orchestrator.stream(body, request),
        media_type="text/event-stream",
        headers=STREAM_HEADERS,
    )
