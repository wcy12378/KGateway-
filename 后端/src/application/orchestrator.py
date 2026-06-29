"""聊天请求应用层编排模块。

本模块负责协调熔断、语义缓存、Agent 执行、LLM 流式生成和观测写入。
它不直接实现 HTTP 路由、存储客户端、检索算法或前端展示逻辑。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Optional

from src.agents.runtime import AgentRuntime, AgentState
from src.application.policies import ModelRoutingPolicy
from src.application.chat_flows import stream_cached_answer, stream_generated_answer
from src.application.stream_contract import error_frame, info_frame, metadata_frame, sse_done, text_frame
from src.application.streaming_tasks import ClientDisconnectedError, race_with_heartbeat, simulate_llm_tokens
from src.core.cache import SemanticCacheManager
from src.core.embedder import embed_text
from src.core.observability import GatewayObserver, observer as default_observer
from src.core.protection import CircuitBreaker, CircuitBreakerOpenError
from src.core.router import ModelRouter
from src.core.schemas import GatewayRequest

logger = logging.getLogger("kagent.application.orchestrator")

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

    async def stream(self, request: GatewayRequest, http_request: Any) -> AsyncGenerator[str, None]:
        trace_ctx = self.observer.start_trace(
            tenant_id=request.tenant_id,
            user_id=request.user_id,
            session_id=request.session_id,
            question=request.question,
        )
        model_name = self.routing_policy.select_model(request)

        self.observer.start_span(trace_ctx, "circuit_breaker_check")
        cb_blocked = self.circuit_breaker is not None and not self.circuit_breaker.allow_request()
        self.observer.finish_span(
            trace_ctx,
            "circuit_breaker_check",
            state=self.circuit_breaker.state.value if self.circuit_breaker else "N/A",
        )

        if cb_blocked:
            remaining = max(
                0,
                self.circuit_breaker.recovery_timeout
                - (time.monotonic() - self.circuit_breaker._last_failure_time),
            )
            message = f"System busy, retry after {remaining:.0f}s."
            async for chunk in simulate_llm_tokens(message):
                yield text_frame(chunk, circuit_breaker=True)
            trace_ctx.cache_hit = False
            trace_ctx.model_used = model_name
            await self.observer.end_trace(trace_ctx)
            yield metadata_frame(
                cache_hit=False,
                circuit_breaker=True,
                trace_id=trace_ctx.trace_id,
                session_id=request.session_id,
            )
            yield sse_done()
            return

        cached_answer: Optional[str] = None
        self.observer.start_span(trace_ctx, "semantic_cache_lookup")
        if self.semantic_cache is not None:
            try:
                query_vector = embed(request.question)
                cached_answer = await self.semantic_cache.get_cache(
                    tenant_id=request.tenant_id,
                    question_vector=query_vector,
                )
            except Exception as exc:
                logger.warning("Semantic cache lookup failed: %s", exc)
        self.observer.finish_span(trace_ctx, "semantic_cache_lookup", hit=cached_answer is not None)

        if cached_answer:
            async for frame in stream_cached_answer(
                self,
                request=request,
                http_request=http_request,
                cached_answer=cached_answer,
                model_name=model_name,
                trace_ctx=trace_ctx,
            ):
                yield frame
            return

        yield info_frame(
            f"Processing via {model_name}...",
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
            yield error_frame(f"Agent error: {exc}", trace_id=trace_ctx.trace_id)
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
        ):
            yield frame
