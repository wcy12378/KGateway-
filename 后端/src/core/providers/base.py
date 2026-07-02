"""LLM Provider 的统一抽象接口。"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from enum import Enum
from typing import AsyncGenerator, Optional

import httpx


class ProviderHealth(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class LLMProvider(ABC):
    """定义不同 LLM 服务商必须实现的聊天能力。"""

    def __init__(self, config: object) -> None:
        self.config = config
        self.health = ProviderHealth.HEALTHY
        self.consecutive_failures = 0
        self.last_failure_time = 0.0
        self.recovery_timeout = 60.0
        self.avg_latency_ms: float | None = None
        self.recovery_probe_in_flight = False
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(120, connect=10),
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    def ready_for_probe(self) -> bool:
        """隔离期结束后允许一次恢复探测。"""
        return (
            self.health == ProviderHealth.UNHEALTHY
            and time.monotonic() - self.last_failure_time >= self.recovery_timeout
        )

    @property
    @abstractmethod
    def name(self) -> str:
        """返回 Provider 的唯一名称。"""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: Optional[list[dict]] = None,
    ) -> dict:
        """非流式调用，返回内容、token 用量和工具调用。"""

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        """流式调用，逐段产出模型文本。"""

    @abstractmethod
    def get_models(self) -> list[str]:
        """返回当前 Provider 可用的模型。"""
