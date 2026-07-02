"""流式任务与客户端断连处理工具。

本模块负责模拟 token 流、调用 LLM 流式接口、监听客户端断连并在工作任务
和断连信号之间做竞态控制。它不负责业务编排、缓存策略或 SSE 业务元数据。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncGenerator

from src.core.providers.factory import ProviderFactory, ProviderUnavailableError

logger = logging.getLogger("kagent.application.streaming_tasks")

HEARTBEAT_INTERVAL_S = 0.2


class ClientDisconnectedError(Exception):
    """客户端断开连接时用于中断当前流式任务的异常。"""


async def simulate_llm_tokens(
    text: str,
    *,
    chars_per_tick: int = 3,
    delay: float = 0.05,
) -> AsyncGenerator[str, None]:
    """在没有真实 LLM key 或降级场景下模拟 token 流。"""

    for i in range(0, len(text), chars_per_tick):
        yield text[i : i + chars_per_tick]
        await asyncio.sleep(delay)


async def stream_llm_api(
    prompt: str,
    *,
    provider_factory: ProviderFactory,
    system_prompt: str = "You are a professional enterprise knowledge assistant.",
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> AsyncGenerator[str, None]:
    """通过当前 LLM Provider 调用流式接口并产出文本 token。"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]
    try:
        async for chunk in provider_factory.chat_stream_with_fallback(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            yield chunk
        return
    except ProviderUnavailableError:
        pass

    logger.warning("所有 LLM Provider 均不可用，使用模拟流")
    async for chunk in simulate_llm_tokens(prompt):
        yield chunk


async def heartbeat_disconnect_monitor(http_request: Any, stop_event: asyncio.Event) -> None:
    """轮询 FastAPI request 状态，并在客户端断开时设置停止信号。"""

    while not stop_event.is_set():
        try:
            if await http_request.is_disconnected():
                stop_event.set()
                return
        except Exception:
            stop_event.set()
            return
        await asyncio.sleep(HEARTBEAT_INTERVAL_S)


async def race_with_heartbeat(http_request: Any, awaitable: Any) -> Any:
    """在业务任务和断连监听之间竞态，优先响应客户端断连。"""

    stop_event = asyncio.Event()
    heartbeat_task = asyncio.create_task(heartbeat_disconnect_monitor(http_request, stop_event))
    work_task = asyncio.create_task(awaitable)

    try:
        done, _ = await asyncio.wait(
            {work_task, heartbeat_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if heartbeat_task in done:
            work_task.cancel()
            await asyncio.gather(work_task, return_exceptions=True)
            raise ClientDisconnectedError("client disconnected")
        return work_task.result()
    finally:
        stop_event.set()
        if not heartbeat_task.done():
            heartbeat_task.cancel()
        if not work_task.done():
            work_task.cancel()
        await asyncio.gather(heartbeat_task, work_task, return_exceptions=True)
