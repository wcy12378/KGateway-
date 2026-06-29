"""聊天子流程流式输出模块。

本模块负责缓存命中答案输出和 Agent 结果生成输出两个子流程。它依赖主编排器
传入的上下文和基础能力，但不负责创建 trace、执行 Agent 或接收 HTTP 请求。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, AsyncGenerator

from src.agents.runtime import AgentState
from src.application.stream_contract import info_frame, metadata_frame, sse_done, text_frame
from src.application.streaming_tasks import (
    heartbeat_disconnect_monitor,
    simulate_llm_tokens,
    stream_llm_api,
)
from src.core.embedder import embed_text
from src.core.schemas import GatewayRequest

logger = logging.getLogger("kagent.application.chat_flows")


def embed(text: str) -> list[float]:
    """对问题文本做向量化，供缓存写入复用。"""

    return embed_text(text)


async def stream_cached_answer(
    orchestrator: Any,
    *,
    request: GatewayRequest,
    http_request: Any,
    cached_answer: str,
    model_name: str,
    trace_ctx: Any,
) -> AsyncGenerator[str, None]:
    """输出语义缓存命中的答案流，并结束 trace。"""

    trace_ctx.cache_hit = True
    trace_ctx.model_used = model_name
    yield info_frame(
        "Cache hit!",
        model=model_name,
        cache_hit=True,
        trace_id=trace_ctx.trace_id,
    )

    sentinel = object()
    queue: asyncio.Queue = asyncio.Queue()
    t0 = time.perf_counter()

    async def producer() -> None:
        try:
            async for chunk in simulate_llm_tokens(cached_answer):
                await queue.put(chunk)
        finally:
            await queue.put(sentinel)

    producer_task = asyncio.create_task(producer())
    stop_event = asyncio.Event()
    heartbeat_task = asyncio.create_task(heartbeat_disconnect_monitor(http_request, stop_event))
    shielded_heartbeat = asyncio.shield(heartbeat_task)

    try:
        while True:
            get_task = asyncio.create_task(queue.get())
            done, _ = await asyncio.wait(
                {get_task, shielded_heartbeat},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if shielded_heartbeat in done:
                get_task.cancel()
                try:
                    await get_task
                except asyncio.CancelledError:
                    pass
                producer_task.cancel()
                try:
                    await producer_task
                except asyncio.CancelledError:
                    pass
                while not queue.empty():
                    queue.get_nowait()
                return

            chunk = get_task.result()
            if chunk is sentinel:
                break
            yield text_frame(chunk)
    finally:
        shielded_heartbeat.cancel()
        try:
            await shielded_heartbeat
        except asyncio.CancelledError:
            pass

    trace_ctx.ttft_ms = (time.perf_counter() - t0) * 1000
    await orchestrator.observer.end_trace(trace_ctx)
    yield metadata_frame(
        routing_decision=model_name,
        cache_hit=True,
        trace_id=trace_ctx.trace_id,
        session_id=request.session_id,
        model=model_name,
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
) -> AsyncGenerator[str, None]:
    """输出 Agent 结果经 LLM 生成后的答案流，并写入缓存和观测数据。"""

    answer = state.final_answer or "Agent produced no final answer."
    t0 = time.perf_counter()
    collected_text = ""
    yield info_frame(
        f"Generating via {model_name}...",
        model=model_name,
        agent_iterations=state.iteration,
        trace_id=trace_ctx.trace_id,
    )

    sentinel = object()
    queue: asyncio.Queue = asyncio.Queue()

    async def producer() -> None:
        try:
            system_prompt = (
                "You are a professional enterprise knowledge assistant. "
                "Answer based on the retrieved context."
            )
            async for chunk in stream_llm_api(answer, system_prompt=system_prompt):
                await queue.put(chunk)
        except Exception as exc:
            logger.exception("LLM streaming failed: %s", exc)
            async for chunk in simulate_llm_tokens(answer):
                await queue.put(chunk)
        finally:
            await queue.put(sentinel)

    producer_task = asyncio.create_task(producer())
    stop_event = asyncio.Event()
    heartbeat_task = asyncio.create_task(heartbeat_disconnect_monitor(http_request, stop_event))
    shielded_heartbeat = asyncio.shield(heartbeat_task)

    try:
        while True:
            get_task = asyncio.create_task(queue.get())
            done, _ = await asyncio.wait(
                {get_task, shielded_heartbeat},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if shielded_heartbeat in done:
                get_task.cancel()
                try:
                    await get_task
                except asyncio.CancelledError:
                    pass
                producer_task.cancel()
                try:
                    await producer_task
                except asyncio.CancelledError:
                    pass
                while not queue.empty():
                    queue.get_nowait()
                return

            chunk = get_task.result()
            if chunk is sentinel:
                break
            collected_text += chunk
            yield text_frame(chunk)
            if not trace_ctx.ttft_ms:
                trace_ctx.ttft_ms = (time.perf_counter() - t0) * 1000
    finally:
        shielded_heartbeat.cancel()
        try:
            await shielded_heartbeat
        except asyncio.CancelledError:
            pass

        if collected_text and orchestrator.semantic_cache is not None:
            try:
                query_vector = embed(request.question)
                await orchestrator.semantic_cache.set_cache(
                    tenant_id=request.tenant_id,
                    question_vector=query_vector,
                    answer=collected_text,
                    question_text=request.question,
                )
            except Exception as exc:
                logger.warning("Semantic cache write failed: %s", exc)

    est_input_tokens = len(request.question) // 2
    est_output_tokens = len(collected_text) // 2
    async with orchestrator.model_router._lock:
        orchestrator.model_router.token_counter.record(model_name, est_input_tokens, est_output_tokens)
    estimated_cost = orchestrator.model_router.token_counter.estimate_cost(model_name)

    trace_ctx.cache_hit = False
    trace_ctx.model_used = model_name
    trace_ctx.total_tokens = est_input_tokens + est_output_tokens
    trace_ctx.estimated_cost_usd = estimated_cost
    await orchestrator.observer.end_trace(trace_ctx)

    yield metadata_frame(
        trace_id=trace_ctx.trace_id,
        routing_decision=model_name,
        model=model_name,
        cache_hit=False,
        agent_iterations=state.iteration,
        agent_steps=len(state.steps),
        total_tokens=est_input_tokens + est_output_tokens,
        estimated_cost_usd=round(estimated_cost, 8),
        ttft_ms=round(trace_ctx.ttft_ms, 2),
        total_latency_ms=round(trace_ctx.total_latency_ms, 2),
        circuit_breaker=False,
        circuit_breaker_state=orchestrator.circuit_breaker.state.value
        if orchestrator.circuit_breaker
        else "N/A",
        session_id=request.session_id,
    )
    yield sse_done()
