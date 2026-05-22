"""SSE 流式传输管道 — Agent Runtime + 语义缓存 + 熔断器全链路。"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from src.agents.runtime import AgentRuntime, AgentState
from src.config import config
from src.core.cache import SemanticCacheManager
from src.core.fusion import reciprocal_rank_fusion
from src.core.observability import observer
from src.core.protection import CircuitBreaker, CircuitBreakerOpenError
from src.core.reranker import Reranker, RerankResult
from src.core.router import ModelRouter
from src.core.schemas import GatewayRequest
from src.db.bm25_client import SparseRetriever

logger = logging.getLogger("kgateway.api.routes")

router = APIRouter(prefix="/api/v1/gateway", tags=["streaming"])

# ── 模块级单例 ──────────────────────────────────────────────────
_model_router: ModelRouter | None = None
_bm25_retriever: SparseRetriever | None = None
_reranker: Reranker | None = None
_agent_runtime: AgentRuntime | None = None
_semantic_cache: SemanticCacheManager | None = None
_circuit_breaker: CircuitBreaker | None = None


def init_router(
    model_router: ModelRouter,
    bm25_retriever: Optional[SparseRetriever] = None,
    reranker: Optional[Reranker] = None,
    agent_runtime: Optional[AgentRuntime] = None,
    semantic_cache: Optional[SemanticCacheManager] = None,
    circuit_breaker: Optional[CircuitBreaker] = None,
) -> None:
    """由 main.py 调用，注入所有组件实例。"""
    global _model_router, _bm25_retriever, _reranker, _agent_runtime, _semantic_cache, _circuit_breaker
    _model_router = model_router
    _bm25_retriever = bm25_retriever
    _reranker = reranker
    _agent_runtime = agent_runtime
    _semantic_cache = semantic_cache
    _circuit_breaker = circuit_breaker


# ── 模拟 Dense 检索 ────────────────────────────────────────────

async def _mock_dense_search(
    *,
    query: str,
    tenant_id: str,
    department: str,
    top_k: int = 10,
) -> List[Dict[str, Any]]:
    """模拟 Dense 向量检索。"""
    await asyncio.sleep(0.01)
    return [
        {"doc_id": f"doc_{i}", "vector_score": 0.9 - i * 0.05, "text": f"向量检索结果 {i}: {query[:30]}", "metadata": {"source": "dense"}}
        for i in range(min(top_k, 5))
    ]


# ── SSE 编码工具 ────────────────────────────────────────────────

def _sse_encode(data: Dict[str, Any]) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _sse_done() -> str:
    return "data: [DONE]\n\n"


# ── 模拟向量生成 ───────────────────────────────────────────────

def _mock_embed(text: str) -> List[float]:
    """模拟文本向量化（生产环境替换为 BGE/Embedding API）。"""
    import hashlib
    h = hashlib.sha256(text.encode()).digest()
    vec = []
    for b in h:
        vec.extend([(b / 255.0) * 2 - 1] * (384 // len(h)))
    return vec[:384]


# ── RAG 混合检索流水线 ─────────────────────────────────────────

async def _rag_pipeline(
    *,
    query: str,
    tenant_id: str,
    department: str,
    top_k: int = 3,
) -> tuple[List[RerankResult], Dict[str, Any]]:
    """完整的 RAG 流水线：Dense + Sparse → RRF → Rerank。"""
    rag_metrics: Dict[str, Any] = {}

    t_dense_start = time.perf_counter()
    dense_task = asyncio.create_task(
        _mock_dense_search(query=query, tenant_id=tenant_id, department=department, top_k=20)
    )

    sparse_results: List[Dict[str, Any]] = []
    if _bm25_retriever is not None:
        bm25_hits = _bm25_retriever.search(tenant_id=tenant_id, department=department, query=query, top_k=20)
        sparse_results = [
            {"doc_id": h.doc_id, "bm25_score": h.score, "text": h.metadata.get("text", ""), "metadata": h.metadata}
            for h in bm25_hits
        ]

    dense_results = await dense_task
    rag_metrics["dense_latency_ms"] = round((time.perf_counter() - t_dense_start) * 1000, 2)
    rag_metrics["dense_hits"] = len(dense_results)
    rag_metrics["sparse_hits"] = len(sparse_results)

    fused = reciprocal_rank_fusion(dense_results=dense_results, sparse_results=sparse_results, k=60, top_k=20)
    rag_metrics["rrf_candidates"] = len(fused)

    rerank_input = [{"doc_id": f.doc_id, "text": f.metadata.get("text", f.doc_id), "metadata": f.metadata or {}} for f in fused]
    rerank_results: List[RerankResult] = []
    if _reranker is not None:
        rerank_results = await _reranker.rerank_documents(query=query, docs=rerank_input)
    else:
        rerank_results = [
            RerankResult(doc_id=f.doc_id, rerank_score=f.rrf_score, text=f.metadata.get("text", ""), metadata=f.metadata or {})
            for f in fused[:top_k]
        ]
    rag_metrics["rerank_output"] = len(rerank_results)

    return rerank_results, rag_metrics


# ── 模拟 LLM 吐字 ──────────────────────────────────────────────

async def _simulate_llm_tokens(
    text: str,
    *,
    chars_per_tick: int = 3,
    delay: float = 0.05,
) -> AsyncGenerator[str, None]:
    for i in range(0, len(text), chars_per_tick):
        yield text[i : i + chars_per_tick]
        await asyncio.sleep(delay)


# ── 核心流式生成器（缓存 → 熔断 → Agent 全链路）────────────────

async def event_generator(
    request: GatewayRequest,
    http_request: Request,
) -> AsyncGenerator[str, None]:
    """异步 SSE 生成器 — 缓存 + 熔断 + Agent Runtime + 链路追踪全链路。"""
    if _model_router is None or _agent_runtime is None:
        yield _sse_encode({"status": "error", "text": "网关未初始化"})
        yield _sse_done()
        return

    # ── 启动链路追踪 ──────────────────────────────────────────
    trace_ctx = observer.start_trace(
        tenant_id=request.tenant_id,
        user_id=request.user_id,
        session_id=request.session_id,
        question=request.question,
    )

    model_name = _model_router._select_model(request)
    cache_hit = False

    # ════════════════════════════════════════════════════════════
    # Phase 0: 熔断器检查
    # ════════════════════════════════════════════════════════════
    observer.start_span(trace_ctx, "circuit_breaker_check")
    cb_blocked = _circuit_breaker is not None and not _circuit_breaker.allow_request()
    observer.finish_span(trace_ctx, "circuit_breaker_check", state=_circuit_breaker.state.value if _circuit_breaker else "N/A")

    if cb_blocked:
        logger.warning("熔断器拦截: tenant=%s user=%s", request.tenant_id, request.user_id)
        remaining = max(0, _circuit_breaker.recovery_timeout - (time.monotonic() - _circuit_breaker._last_failure_time))
        degradation_answer = f"系统繁忙，服务暂时不可用（熔断保护中，预计 {remaining:.0f}s 后恢复）。"
        async for chunk in _simulate_llm_tokens(degradation_answer):
            yield _sse_encode({"text": chunk, "circuit_breaker": True})
        trace_ctx.cache_hit = False
        trace_ctx.model_used = model_name
        trace_result = await observer.end_trace(trace_ctx)
        yield _sse_encode({"status": "metadata", "cache_hit": False, "circuit_breaker": True, "trace_id": trace_ctx.trace_id, "session_id": request.session_id})
        yield _sse_done()
        return

    # ════════════════════════════════════════════════════════════
    # Phase 1: 语义缓存检查
    # ════════════════════════════════════════════════════════════
    cached_answer: Optional[str] = None
    observer.start_span(trace_ctx, "semantic_cache_lookup")
    if _semantic_cache is not None:
        try:
            query_vector = _mock_embed(request.question)
            cached_answer = await _semantic_cache.get_cache(tenant_id=request.tenant_id, question_vector=query_vector)
        except Exception as exc:
            logger.warning("语义缓存检查异常，降级跳过: %s", exc)
    observer.finish_span(trace_ctx, "semantic_cache_lookup", hit=cached_answer is not None)

    if cached_answer:
        cache_hit = True
        trace_ctx.cache_hit = True
        trace_ctx.model_used = model_name
        print(f"\n⚡ [Cache] 语义缓存命中! tenant={request.tenant_id}")
        yield _sse_encode({"status": "Cache hit!", "model": model_name, "cache_hit": True, "trace_id": trace_ctx.trace_id})
        t0 = time.perf_counter()
        collected_text = ""
        try:
            async for chunk in _simulate_llm_tokens(cached_answer):
                if await http_request.is_disconnected(): return
                collected_text += chunk
                yield _sse_encode({"text": chunk})
        except asyncio.CancelledError:
            return
        trace_ctx.ttft_ms = (time.perf_counter() - t0) * 1000
        trace_result = await observer.end_trace(trace_ctx)
        yield _sse_encode({"status": "metadata", "routing_decision": model_name, "cache_hit": True, "trace_id": trace_ctx.trace_id, "session_id": request.session_id})
        yield _sse_done()
        return

    # ════════════════════════════════════════════════════════════
    # Phase 2: Agent Runtime
    # ════════════════════════════════════════════════════════════
    yield _sse_encode({"status": f"Processing via {model_name}...", "model": model_name, "cache_hit": False, "trace_id": trace_ctx.trace_id, "session_id": request.session_id})
    state = AgentState(request=request, history=[], steps=[], next_node="planner_node", final_answer="")

    observer.start_span(trace_ctx, "agent_runtime")
    t_agent_start = time.perf_counter()
    try:
        if _circuit_breaker is not None:
            async with _circuit_breaker:
                state = await _agent_runtime.execute_graph(state)
        else:
            state = await _agent_runtime.execute_graph(state)
    except CircuitBreakerOpenError as exc:
        observer.finish_span(trace_ctx, "agent_runtime", status="circuit_breaker_blocked")
        degradation = f"系统暂时不可用（{exc}），请稍后重试。"
        async for chunk in _simulate_llm_tokens(degradation):
            yield _sse_encode({"text": chunk, "circuit_breaker": True})
        await observer.end_trace(trace_ctx)
        yield _sse_encode({"status": "metadata", "cache_hit": False, "circuit_breaker": True, "trace_id": trace_ctx.trace_id, "session_id": request.session_id})
        yield _sse_done()
        return
    except Exception as exc:
        logger.exception("Agent Runtime 异常: %s", exc)
        observer.finish_span(trace_ctx, "agent_runtime", status="error", error=str(exc))
        await observer.end_trace(trace_ctx)
        yield _sse_encode({"status": "error", "text": f"Agent 异常: {exc}"})
        yield _sse_done()
        return
    observer.finish_span(trace_ctx, "agent_runtime", iterations=state.iteration, steps=len(state.steps))

    # ════════════════════════════════════════════════════════════
    # Phase 3: 流式推送 + 缓存写入
    # ════════════════════════════════════════════════════════════
    answer = state.final_answer or "抱歉，Agent 未能生成有效回答。"
    t0 = time.perf_counter()
    collected_text = ""
    yield _sse_encode({"status": f"Generating via {model_name}...", "agent_iterations": state.iteration, "trace_id": trace_ctx.trace_id})
    try:
        async for chunk in _simulate_llm_tokens(answer):
            if await http_request.is_disconnected():
                print("【警告】监测到客户端断开，已强行终止上游 Token 计费")
                return
            collected_text += chunk
            yield _sse_encode({"text": chunk})
            if not trace_ctx.ttft_ms:
                trace_ctx.ttft_ms = (time.perf_counter() - t0) * 1000
    except asyncio.CancelledError:
        return
    except Exception as exc:
        logger.exception("流式生成异常: %s", exc)
        yield _sse_encode({"status": "error", "text": f"生成异常: {exc}"})
        yield _sse_done()
        return

    est_input_tokens = len(request.question) // 2
    est_output_tokens = len(collected_text) // 2
    async with _model_router._lock:
        _model_router.token_counter.record(model_name, est_input_tokens, est_output_tokens)
    estimated_cost = _model_router.token_counter.estimate_cost(model_name)

    # 异步写入缓存
    observer.start_span(trace_ctx, "cache_write")
    if _semantic_cache is not None and collected_text:
        try:
            query_vector = _mock_embed(request.question)
            await _semantic_cache.set_cache(tenant_id=request.tenant_id, question_vector=query_vector, answer=collected_text, question_text=request.question)
        except Exception as exc:
            logger.warning("语义缓存写入异常: %s", exc)
    observer.finish_span(trace_ctx, "cache_write")

    # 更新 trace 上下文
    trace_ctx.cache_hit = cache_hit
    trace_ctx.model_used = model_name
    trace_ctx.total_tokens = est_input_tokens + est_output_tokens
    trace_ctx.estimated_cost_usd = estimated_cost
    trace_result = await observer.end_trace(trace_ctx)

    metadata = {
        "status": "metadata",
        "trace_id": trace_ctx.trace_id,
        "routing_decision": model_name,
        "cache_hit": cache_hit,
        "agent_iterations": state.iteration,
        "agent_steps": len(state.steps),
        "total_tokens": est_input_tokens + est_output_tokens,
        "estimated_cost_usd": round(estimated_cost, 8),
        "ttft_ms": round(trace_ctx.ttft_ms, 2),
        "total_latency_ms": round(trace_ctx.total_latency_ms, 2),
        "circuit_breaker": _circuit_breaker.state.value if _circuit_breaker else "N/A",
        "session_id": request.session_id,
    }
    yield _sse_encode(metadata)
    yield _sse_done()


# ── API 端点 ────────────────────────────────────────────────────

@router.post("/stream", summary="SSE 流式网关（缓存 + 熔断 + Agent 全链路）")
async def gateway_stream(
    body: GatewayRequest,
    request: Request,
) -> StreamingResponse:
    """接收 GatewayRequest，经缓存/熔断/Agent 全链路处理后返回 SSE 流式响应。"""
    logger.info(
        "stream request: user=%s tenant=%s dept=%s adv=%s q_len=%d",
        body.user_id, body.tenant_id, body.department.value,
        body.advanced_reasoning, len(body.question),
    )
    return StreamingResponse(
        event_generator(body, request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
