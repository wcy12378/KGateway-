"""聊天请求应用层编排模块。

本模块负责协调熔断、语义缓存、Agent 执行、LLM 流式生成和观测写入。
它不直接实现 HTTP 路由、存储客户端、检索算法或前端展示逻辑。
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Optional

from src.agents.runtime import AgentRuntime, AgentState
from src.application.policies import ModelRoutingPolicy
from src.application.chat_flows import (
    stream_cached_answer,
    stream_fast_lane_answer,
    stream_generated_answer,
    stream_provider_answer,
)
from src.application.stream_contract import error_frame, info_frame, metadata_frame, sse_done, text_frame
from src.application.streaming_tasks import ClientDisconnectedError, race_with_heartbeat, simulate_llm_tokens
from src.core.cache import SemanticCacheManager
from src.core.embedder import embed_text
from src.core.observability import GatewayObserver, observer as default_observer
from src.core.protection import CircuitBreaker, CircuitBreakerOpenError
from src.core.router import ModelRouter
from src.core.schemas import GatewayRequest
from src.config import config

logger = logging.getLogger("kagent.application.orchestrator")

_KNOWLEDGE_INTENT = re.compile(r"知识库|内部|文档|规范|制度|政策|合同|流程|报销|请假|检索|查找|资料")
_TOOL_INTENT = re.compile(r"调用工具|联网|互联网|网页|计算|算一下|工作流|多步骤|审计")
_NON_CACHEABLE_INTENT = re.compile(r"现在|当前|今天|最新|实时|天气|汇率|股价|新闻")

def embed(text: str) -> list[float]:
    return embed_text(text)


@dataclass
class ChatOrchestrator:
    model_router: ModelRouter
    agent_runtime: AgentRuntime
    semantic_cache: Optional[SemanticCacheManager] = None
    circuit_breaker: Optional[CircuitBreaker] = None
    observer: GatewayObserver = field(default_factory=lambda: default_observer)
    routing_policy: ModelRoutingPolicy = field(default_factory=ModelRoutingPolicy)
    provider_factory: Any = None
    rag_service: Any = None
    fast_lane: Any = None
    background_tasks: set[asyncio.Task] = field(default_factory=set, repr=False)

    async def drain_background_tasks(self) -> None:
        """等待已调度的后台写入结束。"""
        if not self.background_tasks:
            return
        tasks = tuple(self.background_tasks)
        await asyncio.gather(*tasks, return_exceptions=True)
        self.background_tasks.difference_update(tasks)

    @staticmethod
    def execution_path(request: GatewayRequest) -> str:
        if request.advanced_reasoning or _TOOL_INTENT.search(request.question):
            return "agent"
        if _KNOWLEDGE_INTENT.search(request.question):
            return "knowledge"
        return "direct"

    async def stream(self, request: GatewayRequest, http_request: Any) -> AsyncGenerator[str, None]:
        trace_ctx = self.observer.start_trace(
            tenant_id=request.tenant_id,
            user_id=request.user_id,
            session_id=request.session_id,
            question=request.question,
        )
        model_name = self.routing_policy.select_model(request)

        yield info_frame(
            "Checking cache...",
            phase="checking_cache",
            trace_id=trace_ctx.trace_id,
            session_id=request.session_id,
        )

        execution_path = self.execution_path(request)
        department = getattr(request.department, "value", request.department)
        cache_allowed = execution_path != "agent" and not _NON_CACHEABLE_INTENT.search(request.question)
        cache_enabled = (
            cache_allowed
            and self.semantic_cache is not None
            and getattr(self.semantic_cache, "connected", True)
        )
        cached_answer: Optional[str] = None
        query_vector: list[float] | None = None
        cache_started = time.perf_counter()
        timeout_s = max(config.semantic_cache_timeout_ms, 1) / 1000
        self.observer.start_span(trace_ctx, "semantic_cache_lookup")

        if cache_enabled:
            try:
                cached_answer = await asyncio.wait_for(
                    self.semantic_cache.get_exact_cache(
                        tenant_id=request.tenant_id,
                        question_text=request.question,
                        department=department,
                    ),
                    timeout=timeout_s,
                )
            except asyncio.TimeoutError:
                logger.warning("Exact cache lookup exceeded %dms; bypassing", config.semantic_cache_timeout_ms)
            except Exception as exc:
                logger.warning("Exact cache lookup failed: %s", exc)

        if cached_answer:
            trace_ctx.cache_lookup_ms = (time.perf_counter() - cache_started) * 1000
            self.observer.finish_span(trace_ctx, "semantic_cache_lookup", hit=True, hit_type="exact")
            async for frame in stream_cached_answer(
                self,
                request=request,
                http_request=http_request,
                cached_answer=cached_answer,
                model_name=model_name,
                trace_ctx=trace_ctx,
                cache_hit_type="exact",
            ):
                yield frame
            return

        if config.fast_path_enabled and self.fast_lane is not None:
            try:
                fast_result = await self.fast_lane.try_answer(request)
            except Exception as exc:
                logger.warning("Fast lane failed; continuing: %s", exc)
                fast_result = None
            if fast_result is not None:
                trace_ctx.cache_lookup_ms = (time.perf_counter() - cache_started) * 1000
                self.observer.finish_span(trace_ctx, "semantic_cache_lookup", hit=False)
                async for frame in stream_fast_lane_answer(
                    self,
                    request=request,
                    answer=fast_result.answer,
                    response_source=fast_result.source,
                    model_name=model_name,
                    trace_ctx=trace_ctx,
                ):
                    yield frame
                return

        semantic_enabled = cache_enabled and getattr(self.semantic_cache, "semantic_ready", True)
        if semantic_enabled:
            try:
                self.observer.start_span(trace_ctx, "embedding")
                query_vector = await asyncio.to_thread(embed, request.question)
                self.observer.finish_span(trace_ctx, "embedding")
                self.observer.start_span(trace_ctx, "redis_semantic_cache")
                cached_answer = await asyncio.wait_for(
                    self.semantic_cache.get_cache(
                        tenant_id=request.tenant_id,
                        question_vector=query_vector,
                        department=department,
                    ),
                    timeout=timeout_s,
                )
                self.observer.finish_span(trace_ctx, "redis_semantic_cache")
            except asyncio.TimeoutError:
                logger.warning("Semantic cache lookup exceeded %dms; bypassing", config.semantic_cache_timeout_ms)
            except Exception as exc:
                logger.warning("Semantic cache lookup failed: %s", exc)

        trace_ctx.cache_lookup_ms = (time.perf_counter() - cache_started) * 1000
        self.observer.finish_span(trace_ctx, "semantic_cache_lookup", hit=cached_answer is not None)
        if cached_answer:
            async for frame in stream_cached_answer(
                self,
                request=request,
                http_request=http_request,
                cached_answer=cached_answer,
                model_name=model_name,
                trace_ctx=trace_ctx,
                cache_hit_type="semantic",
            ):
                yield frame
            return

        if config.fast_path_enabled and self.provider_factory is not None and execution_path != "agent":
            context_text = ""
            if execution_path == "knowledge" and self.rag_service is not None:
                yield info_frame(
                    "Retrieving enterprise knowledge...",
                    phase="retrieving_knowledge",
                    trace_id=trace_ctx.trace_id,
                )
                if query_vector is None:
                    self.observer.start_span(trace_ctx, "embedding")
                    query_vector = await asyncio.to_thread(embed, request.question)
                    self.observer.finish_span(trace_ctx, "embedding")
                self.observer.start_span(trace_ctx, "rag_retrieval")
                try:
                    results, rag_metrics = await self.rag_service.retrieve(
                        query=request.question,
                        tenant_id=request.tenant_id,
                        department=department,
                        top_k=3,
                        query_vector=query_vector,
                    )
                    context_text = "\n\n".join(result.text for result in results if result.text)
                    self.observer.finish_span(trace_ctx, "rag_retrieval", **rag_metrics)
                except Exception as exc:
                    logger.warning("Fast-path RAG failed; continuing without context: %s", exc)
                    self.observer.finish_span(trace_ctx, "rag_retrieval", status="error", error=str(exc))

            if execution_path == "knowledge" and not context_text:
                async for frame in stream_fast_lane_answer(
                    self,
                    request=request,
                    answer="未检索到可用的企业知识依据，无法可靠回答该问题。",
                    response_source="knowledge_unavailable",
                    model_name=model_name,
                    trace_ctx=trace_ctx,
                ):
                    yield frame
                return

            async for frame in stream_provider_answer(
                self,
                request=request,
                http_request=http_request,
                model_name=model_name,
                trace_ctx=trace_ctx,
                context_text=context_text,
                query_vector=query_vector,
                cache_write_enabled=cache_allowed,
            ):
                yield frame
            return

        yield info_frame(
            f"Processing via {model_name}...",
            phase="running_agent",
            model=model_name,
            cache_hit=False,
            trace_id=trace_ctx.trace_id,
            session_id=request.session_id,
        )

        state = AgentState(
            request=request,
            history=[],
            steps=[],
            next_node="planner_node",
            final_answer="",
            trace_id=trace_ctx.trace_id,
        )
        self.observer.start_span(trace_ctx, "agent_runtime")
        try:
            if self.circuit_breaker is not None:
                async with self.circuit_breaker:
                    state = await race_with_heartbeat(http_request, self.agent_runtime.execute_graph(state))
            else:
                state = await race_with_heartbeat(http_request, self.agent_runtime.execute_graph(state))
        except ClientDisconnectedError:
            self.observer.finish_span(trace_ctx, "agent_runtime", status="client_disconnected")
            await self.observer.end_trace(trace_ctx)
            return
        except CircuitBreakerOpenError as exc:
            self.observer.finish_span(trace_ctx, "agent_runtime", status="circuit_breaker_blocked")
            async for chunk in simulate_llm_tokens(f"System unavailable: {exc}"):
                yield text_frame(chunk, circuit_breaker=True)
            await self.observer.end_trace(trace_ctx)
            yield metadata_frame(
                cache_hit=False,
                circuit_breaker=True,
                trace_id=trace_ctx.trace_id,
                session_id=request.session_id,
            )
            yield sse_done()
            return
        except Exception as exc:
            logger.exception("Agent runtime failed: %s", exc)
            self.observer.finish_span(trace_ctx, "agent_runtime", status="error", error=str(exc))
            await self.observer.end_trace(trace_ctx)
            yield error_frame("Agent execution failed", trace_id=trace_ctx.trace_id)
            yield sse_done()
            return

        self.observer.finish_span(
            trace_ctx,
            "agent_runtime",
            iterations=state.iteration,
            steps=len(state.steps),
        )

        async for frame in stream_generated_answer(
            self,
            request=request,
            http_request=http_request,
            state=state,
            model_name=model_name,
            trace_ctx=trace_ctx,
            query_vector=query_vector,
        ):
            yield frame
