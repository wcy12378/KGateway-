"""聊天子流程流式输出模块。

本模块负责缓存命中答案输出和 Agent 结果生成输出两个子流程。它依赖主编排器
传入的上下文和基础能力，但不负责创建 trace、执行 Agent 或接收 HTTP 请求。
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import AsyncExitStack
from typing import Any, AsyncGenerator

from src.agents.runtime import AgentState
from src.application.stream_contract import (
    error_frame,
    heartbeat_frame,
    info_frame,
    metadata_frame,
    sse_done,
    text_frame,
)
from src.application.streaming_tasks import (
    ClientDisconnectedError,
    heartbeat_disconnect_monitor,
    simulate_llm_tokens,
)
from src.config import config
from src.core.embedder import embed_text
from src.core.schemas import GatewayRequest

logger = logging.getLogger("kagent.application.chat_flows")
SSE_KEEPALIVE_INTERVAL_S = 15.0


def embed(text: str) -> list[float]:
    """对问题文本做向量化，供缓存写入复用。"""

    return embed_text(text)


async def _write_caches(
    orchestrator: Any,
    request: GatewayRequest,
    answer: str,
    query_vector: list[float] | None,
) -> None:
    if orchestrator.semantic_cache is None or not answer:
        return
    try:
        vector = query_vector or await asyncio.to_thread(embed, request.question)
        department = getattr(request.department, "value", request.department)
        await asyncio.gather(
            orchestrator.semantic_cache.set_exact_cache(
                tenant_id=request.tenant_id,
                question_text=request.question,
                answer=answer,
                department=department,
            ),
            orchestrator.semantic_cache.set_cache(
                tenant_id=request.tenant_id,
                question_vector=vector,
                answer=answer,
                question_text=request.question,
                department=department,
            ),
        )
    except Exception as exc:
        logger.warning("Background cache write failed: %s", exc)


def _schedule_cache_write(
    orchestrator: Any,
    request: GatewayRequest,
    answer: str,
    query_vector: list[float] | None,
) -> None:
    task = asyncio.create_task(_write_caches(orchestrator, request, answer, query_vector))
    orchestrator.background_tasks.add(task)

    def finished(done_task: asyncio.Task) -> None:
        orchestrator.background_tasks.discard(done_task)
        if not done_task.cancelled():
            done_task.exception()

    task.add_done_callback(finished)


async def stream_cached_answer(
    orchestrator: Any,
    *,
    request: GatewayRequest,
    http_request: Any,
    cached_answer: str,
    model_name: str,
    trace_ctx: Any,
    cache_hit_type: str = "semantic",
) -> AsyncGenerator[str, None]:
    """输出语义缓存命中的答案流，并结束 trace。"""

    trace_ctx.cache_hit = True
    trace_ctx.cache_hit_type = cache_hit_type
    trace_ctx.response_source = "cache"
    trace_ctx.model_used = model_name
    yield info_frame(
        "Cache hit!",
        phase="cache_hit",
        model=model_name,
        cache_hit_type=cache_hit_type,
        response_source="cache",
        cache_hit=True,
        trace_id=trace_ctx.trace_id,
    )

    sentinel = object()
    queue: asyncio.Queue = asyncio.Queue()

    async def producer() -> None:
        try:
            for index in range(0, len(cached_answer), 48):
                await queue.put(cached_answer[index : index + 48])
                await asyncio.sleep(0)
        finally:
            await queue.put(sentinel)

    producer_task = asyncio.create_task(producer())
    stop_event = asyncio.Event()
    heartbeat_task = asyncio.create_task(heartbeat_disconnect_monitor(http_request, stop_event))
    get_task: asyncio.Task | None = None

    try:
        while True:
            get_task = asyncio.create_task(queue.get())
            done, _ = await asyncio.wait(
                {get_task, heartbeat_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if heartbeat_task in done:
                get_task.cancel()
                await asyncio.gather(get_task, return_exceptions=True)
                producer_task.cancel()
                await asyncio.gather(producer_task, return_exceptions=True)
                while not queue.empty():
                    queue.get_nowait()
                return

            chunk = get_task.result()
            if chunk is sentinel:
                break
            if not trace_ctx.ttft_ms:
                trace_ctx.ttft_ms = (time.perf_counter() - trace_ctx.t_start) * 1000
            yield text_frame(chunk)
    finally:
        stop_event.set()
        for task in (get_task, producer_task, heartbeat_task):
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(
            *(task for task in (get_task, producer_task, heartbeat_task) if task is not None),
            return_exceptions=True,
        )

    await orchestrator.observer.end_trace(trace_ctx)
    yield metadata_frame(
        routing_decision=model_name,
        cache_hit=True,
        cache_hit_type=cache_hit_type,
        response_source="cache",
        trace_id=trace_ctx.trace_id,
        session_id=request.session_id,
        model=model_name,
        ttft_ms=round(trace_ctx.ttft_ms, 2),
        total_latency_ms=round(trace_ctx.total_latency_ms, 2),
        provider_ttft_ms=0.0,
        cache_lookup_ms=round(trace_ctx.cache_lookup_ms, 2),
        app_overhead_ms=round(trace_ctx.app_overhead_ms, 2),
    )
    yield sse_done()


async def stream_fast_lane_answer(
    orchestrator: Any,
    *,
    request: GatewayRequest,
    answer: str,
    response_source: str,
    model_name: str,
    trace_ctx: Any,
) -> AsyncGenerator[str, None]:
    """Return a deterministic answer without invoking a provider or Agent."""

    yield info_frame("Running safe fast lane...", phase="running_fast_lane")
    trace_ctx.ttft_ms = (time.perf_counter() - trace_ctx.t_start) * 1000
    yield text_frame(answer)
    trace_ctx.cache_hit = False
    trace_ctx.cache_hit_type = "none"
    trace_ctx.response_source = response_source
    trace_ctx.model_used = response_source
    await orchestrator.observer.end_trace(trace_ctx)
    yield metadata_frame(
        trace_id=trace_ctx.trace_id,
        routing_decision=model_name,
        model="",
        provider="",
        cache_hit=False,
        cache_hit_type="none",
        response_source=response_source,
        agent_iterations=0,
        agent_steps=0,
        total_tokens=0,
        estimated_cost_usd=0.0,
        ttft_ms=round(trace_ctx.ttft_ms, 2),
        total_latency_ms=round(trace_ctx.total_latency_ms, 2),
        provider_ttft_ms=0.0,
        cache_lookup_ms=round(trace_ctx.cache_lookup_ms, 2),
        app_overhead_ms=round(trace_ctx.app_overhead_ms, 2),
        circuit_breaker=False,
        session_id=request.session_id,
    )
    yield sse_done()


async def stream_provider_answer(
    orchestrator: Any,
    *,
    request: GatewayRequest,
    http_request: Any,
    model_name: str,
    trace_ctx: Any,
    context_text: str = "",
    query_vector: list[float] | None = None,
    cache_write_enabled: bool = True,
) -> AsyncGenerator[str, None]:
    """Stream one provider call directly to SSE for the interactive fast path."""
    system_prompt = "You are a concise enterprise knowledge assistant."
    if context_text:
        system_prompt += " Answer only from the supplied enterprise context and say when evidence is missing."
    user_content = request.question
    if context_text:
        user_content = f"Enterprise context:\n{context_text[:6000]}\n\nQuestion:\n{request.question}"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    provider_name = ""
    actual_model = ""

    def selected(provider: str, model: str) -> None:
        nonlocal provider_name, actual_model
        provider_name = provider
        actual_model = model

    yield info_frame(
        f"Streaming via {model_name}...",
        phase="waiting_provider",
        model=model_name,
        trace_id=trace_ctx.trace_id,
        session_id=request.session_id,
    )
    collected_text = ""
    provider_started = time.perf_counter()
    orchestrator.observer.start_span(trace_ctx, "provider_stream")
    try:
        async with AsyncExitStack() as stack:
            if orchestrator.circuit_breaker is not None:
                await stack.enter_async_context(orchestrator.circuit_breaker)
            provider_stream = orchestrator.provider_factory.chat_stream_with_fallback(
                messages,
                on_provider_selected=selected,
                max_tokens=config.interactive_max_tokens,
            ).__aiter__()
            disconnect_stop = asyncio.Event()
            disconnect_task = asyncio.create_task(
                heartbeat_disconnect_monitor(http_request, disconnect_stop)
            )

            async def stop_disconnect_monitor() -> None:
                disconnect_stop.set()
                if not disconnect_task.done():
                    disconnect_task.cancel()
                await asyncio.gather(disconnect_task, return_exceptions=True)

            stack.push_async_callback(stop_disconnect_monitor)
            while True:
                try:
                    next_chunk = asyncio.create_task(anext(provider_stream))
                    try:
                        while True:
                            done, _ = await asyncio.wait(
                                {next_chunk, disconnect_task},
                                timeout=SSE_KEEPALIVE_INTERVAL_S,
                                return_when=asyncio.FIRST_COMPLETED,
                            )
                            if disconnect_task in done:
                                next_chunk.cancel()
                                await asyncio.gather(next_chunk, return_exceptions=True)
                                raise ClientDisconnectedError("client disconnected")
                            if next_chunk in done:
                                chunk = next_chunk.result()
                                break
                            yield heartbeat_frame()
                    except BaseException:
                        if not next_chunk.done():
                            next_chunk.cancel()
                            await asyncio.gather(next_chunk, return_exceptions=True)
                        raise
                except StopAsyncIteration:
                    break
                except ClientDisconnectedError:
                    await provider_stream.aclose()
                    orchestrator.observer.finish_span(
                        trace_ctx,
                        "provider_stream",
                        status="client_disconnected",
                    )
                    await orchestrator.observer.end_trace(trace_ctx)
                    return
                if not trace_ctx.provider_ttft_ms:
                    trace_ctx.provider_ttft_ms = (time.perf_counter() - provider_started) * 1000
                    trace_ctx.ttft_ms = (time.perf_counter() - trace_ctx.t_start) * 1000
                collected_text += chunk
                yield text_frame(chunk)
    except Exception as exc:
        orchestrator.observer.finish_span(trace_ctx, "provider_stream", status="error", error=str(exc))
        await orchestrator.observer.end_trace(trace_ctx)
        yield error_frame("Provider service unavailable", trace_id=trace_ctx.trace_id)
        yield sse_done()
        return

    trace_ctx.provider_total_ms = (time.perf_counter() - provider_started) * 1000
    orchestrator.observer.finish_span(
        trace_ctx,
        "provider_stream",
        provider=provider_name,
        model=actual_model,
    )
    actual_model = actual_model or model_name
    if cache_write_enabled:
        _schedule_cache_write(orchestrator, request, collected_text, query_vector)

    est_input_tokens = len(user_content) // 2
    est_output_tokens = len(collected_text) // 2
    async with orchestrator.model_router._lock:
        orchestrator.model_router.token_counter.record(actual_model, est_input_tokens, est_output_tokens)
    pricing = config.pricing_for(actual_model)
    estimated_cost = (
        (est_input_tokens / 1000) * pricing.input_price_per_1k
        + (est_output_tokens / 1000) * pricing.output_price_per_1k
    )
    trace_ctx.cache_hit = False
    trace_ctx.cache_hit_type = "none"
    trace_ctx.response_source = "provider"
    trace_ctx.model_used = actual_model
    trace_ctx.total_tokens = est_input_tokens + est_output_tokens
    trace_ctx.estimated_cost_usd = estimated_cost
    await orchestrator.observer.end_trace(trace_ctx)

    yield metadata_frame(
        trace_id=trace_ctx.trace_id,
        routing_decision=model_name,
        model=actual_model,
        provider=provider_name,
        cache_hit=False,
        cache_hit_type="none",
        response_source="provider",
        agent_iterations=0,
        agent_steps=0,
        total_tokens=trace_ctx.total_tokens,
        estimated_cost_usd=round(estimated_cost, 8),
        ttft_ms=round(trace_ctx.ttft_ms, 2),
        total_latency_ms=round(trace_ctx.total_latency_ms, 2),
        provider_ttft_ms=round(trace_ctx.provider_ttft_ms, 2),
        cache_lookup_ms=round(trace_ctx.cache_lookup_ms, 2),
        app_overhead_ms=round(trace_ctx.app_overhead_ms, 2),
        circuit_breaker=False,
        circuit_breaker_state=orchestrator.circuit_breaker.state.value if orchestrator.circuit_breaker else "N/A",
        session_id=request.session_id,
    )
    yield sse_done()


async def stream_generated_answer(
    orchestrator: Any,
    *,
    request: GatewayRequest,
    http_request: Any,
    state: AgentState,
    model_name: str,
    trace_ctx: Any,
    query_vector: list[float] | None = None,
) -> AsyncGenerator[str, None]:
    """输出 Agent 结果经 LLM 生成后的答案流，并写入缓存和观测数据。"""

    answer = state.final_answer or "Agent produced no final answer."
    collected_text = ""
    actual_model = state.model_used or model_name
    actual_provider = state.provider_used
    yield info_frame(
        f"Generating via {actual_model}...",
        phase="running_agent",
        model=actual_model,
        provider=actual_provider,
        agent_iterations=state.iteration,
        trace_id=trace_ctx.trace_id,
    )

    sentinel = object()
    queue: asyncio.Queue = asyncio.Queue()

    async def producer() -> None:
        try:
            for index in range(0, len(answer), 24):
                await queue.put(answer[index : index + 24])
                await asyncio.sleep(0)
        finally:
            await queue.put(sentinel)

    producer_task = asyncio.create_task(producer())
    stop_event = asyncio.Event()
    heartbeat_task = asyncio.create_task(heartbeat_disconnect_monitor(http_request, stop_event))
    get_task: asyncio.Task | None = None

    try:
        while True:
            get_task = asyncio.create_task(queue.get())
            done, _ = await asyncio.wait(
                {get_task, heartbeat_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if heartbeat_task in done:
                get_task.cancel()
                await asyncio.gather(get_task, return_exceptions=True)
                producer_task.cancel()
                await asyncio.gather(producer_task, return_exceptions=True)
                while not queue.empty():
                    queue.get_nowait()
                return

            chunk = get_task.result()
            if chunk is sentinel:
                break
            collected_text += chunk
            yield text_frame(chunk)
    finally:
        stop_event.set()
        for task in (get_task, producer_task, heartbeat_task):
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(
            *(task for task in (get_task, producer_task, heartbeat_task) if task is not None),
            return_exceptions=True,
        )

    est_input_tokens = len(request.question) // 2
    est_output_tokens = len(collected_text) // 2
    async with orchestrator.model_router._lock:
        orchestrator.model_router.token_counter.record(actual_model, est_input_tokens, est_output_tokens)
    pricing = config.pricing_for(actual_model)
    estimated_cost = (
        (est_input_tokens / 1000) * pricing.input_price_per_1k
        + (est_output_tokens / 1000) * pricing.output_price_per_1k
    )

    trace_ctx.cache_hit = False
    trace_ctx.cache_hit_type = "none"
    trace_ctx.response_source = "agent"
    trace_ctx.model_used = actual_model
    agent_span = trace_ctx.spans.get("agent_runtime")
    if not trace_ctx.ttft_ms and agent_span is not None:
        trace_ctx.ttft_ms = agent_span.duration_ms
    trace_ctx.total_tokens = est_input_tokens + est_output_tokens
    trace_ctx.estimated_cost_usd = estimated_cost
    await orchestrator.observer.end_trace(trace_ctx)

    yield metadata_frame(
        trace_id=trace_ctx.trace_id,
        routing_decision=model_name,
        model=actual_model,
        provider=actual_provider,
        cache_hit=False,
        cache_hit_type="none",
        response_source="agent",
        agent_iterations=state.iteration,
        agent_steps=len(state.steps),
        total_tokens=est_input_tokens + est_output_tokens,
        estimated_cost_usd=round(estimated_cost, 8),
        ttft_ms=round(trace_ctx.ttft_ms, 2),
        total_latency_ms=round(trace_ctx.total_latency_ms, 2),
        provider_ttft_ms=round(trace_ctx.provider_ttft_ms, 2),
        cache_lookup_ms=round(trace_ctx.cache_lookup_ms, 2),
        app_overhead_ms=round(trace_ctx.app_overhead_ms, 2),
        circuit_breaker=False,
        circuit_breaker_state=orchestrator.circuit_breaker.state.value
        if orchestrator.circuit_breaker
        else "N/A",
        session_id=request.session_id,
    )
    yield sse_done()
