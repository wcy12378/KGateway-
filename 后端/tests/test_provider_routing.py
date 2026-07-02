"""多 Provider 健康路由与 fallback 测试。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, AsyncGenerator

import pytest

from src.core.agent.react_agent import ReActAgent
from src.core.providers.base import LLMProvider, ProviderHealth
from src.core.providers.factory import ProviderFactory, ProviderUnavailableError
from src.core.tools.registry import ToolRegistry


class StubProvider(LLMProvider):
    def __init__(
        self,
        name: str,
        *,
        chat_results: list[dict | Exception] | None = None,
        stream_results: list[list[str | Exception] | Exception] | None = None,
    ) -> None:
        super().__init__(SimpleNamespace())
        self._name = name
        self.chat_results = list(chat_results or [])
        self.stream_results = list(stream_results or [])
        self.chat_calls = 0
        self.stream_calls = 0

    @property
    def name(self) -> str:
        return self._name

    async def chat(self, messages: list[dict], **_: Any) -> dict:
        self.chat_calls += 1
        result = self.chat_results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    async def chat_stream(self, messages: list[dict], **_: Any) -> AsyncGenerator[str, None]:
        self.stream_calls += 1
        result = self.stream_results.pop(0)
        if isinstance(result, Exception):
            raise result
        for chunk in result:
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk

    def get_models(self) -> list[str]:
        return [f"{self.name}-model"]


def make_factory(
    providers: dict[str, StubProvider],
    *,
    default: str = "openai",
    strategy: str = "priority",
) -> ProviderFactory:
    config = SimpleNamespace(
        kagent_llm_provider=default,
        provider_routing_strategy=strategy,
        deepseek_api_key="configured" if "deepseek" in providers else "",
        openai_api_key="configured" if "openai" in providers else "",
        gemini_api_key="configured" if "gemini" in providers else "",
    )
    factory = ProviderFactory()
    factory.init(config)
    factory._providers.update(providers)
    return factory


@pytest.mark.asyncio
async def test_chat_falls_back_to_next_provider() -> None:
    openai = StubProvider("openai", chat_results=[RuntimeError("quota exceeded")])
    deepseek = StubProvider("deepseek", chat_results=[{"content": "fallback answer", "tool_calls": []}])
    factory = make_factory({"openai": openai, "deepseek": deepseek})

    response = await factory.chat_with_fallback([{"role": "user", "content": "hello"}])

    assert response["content"] == "fallback answer"
    assert openai.health == ProviderHealth.DEGRADED
    assert openai.consecutive_failures == 1
    assert deepseek.health == ProviderHealth.HEALTHY
    assert openai.chat_calls == deepseek.chat_calls == 1


@pytest.mark.asyncio
async def test_three_failures_isolate_provider() -> None:
    openai = StubProvider(
        "openai",
        chat_results=[RuntimeError("failure 1"), RuntimeError("failure 2"), RuntimeError("failure 3")],
    )
    deepseek = StubProvider(
        "deepseek",
        chat_results=[{"content": "ok"}] * 4,
    )
    factory = make_factory({"openai": openai, "deepseek": deepseek})

    for _ in range(3):
        await factory.chat_with_fallback([{"role": "user", "content": "hello"}])
    await factory.chat_with_fallback([{"role": "user", "content": "hello"}])

    assert openai.health == ProviderHealth.UNHEALTHY
    assert openai.chat_calls == 3
    assert deepseek.chat_calls == 4
    assert factory.get_provider().name == "deepseek"


@pytest.mark.asyncio
async def test_isolated_provider_recovers_after_timeout() -> None:
    openai = StubProvider("openai", chat_results=[{"content": "recovered"}])
    deepseek = StubProvider("deepseek", chat_results=[])
    factory = make_factory({"openai": openai, "deepseek": deepseek})
    openai.health = ProviderHealth.UNHEALTHY
    openai.consecutive_failures = 3
    openai.last_failure_time = 1.0
    openai.recovery_timeout = 0.0

    response = await factory.chat_with_fallback([{"role": "user", "content": "probe"}])

    assert response["content"] == "recovered"
    assert openai.health == ProviderHealth.HEALTHY
    assert openai.consecutive_failures == 0


def test_latency_strategy_selects_fastest_healthy_provider() -> None:
    openai = StubProvider("openai")
    deepseek = StubProvider("deepseek")
    factory = make_factory({"openai": openai, "deepseek": deepseek}, strategy="latency")
    factory.record_success("openai", 250)
    factory.record_success("deepseek", 80)

    assert factory.get_provider().name == "deepseek"


@pytest.mark.asyncio
async def test_stream_falls_back_before_first_chunk() -> None:
    openai = StubProvider("openai", stream_results=[RuntimeError("rate limited")])
    deepseek = StubProvider("deepseek", stream_results=[["fall", "back"]])
    factory = make_factory({"openai": openai, "deepseek": deepseek})

    chunks = [
        chunk
        async for chunk in factory.chat_stream_with_fallback(
            [{"role": "user", "content": "hello"}]
        )
    ]

    assert chunks == ["fall", "back"]
    assert openai.health == ProviderHealth.DEGRADED
    assert deepseek.health == ProviderHealth.HEALTHY


@pytest.mark.asyncio
async def test_stream_does_not_mix_provider_output_after_first_chunk() -> None:
    openai = StubProvider(
        "openai",
        stream_results=[["partial", RuntimeError("connection lost")]],
    )
    deepseek = StubProvider("deepseek", stream_results=[["replacement"]])
    factory = make_factory({"openai": openai, "deepseek": deepseek})
    received: list[str] = []

    with pytest.raises(RuntimeError, match="connection lost"):
        async for chunk in factory.chat_stream_with_fallback(
            [{"role": "user", "content": "hello"}]
        ):
            received.append(chunk)

    assert received == ["partial"]
    assert deepseek.stream_calls == 0


@pytest.mark.asyncio
async def test_all_provider_failures_raise_unavailable() -> None:
    openai = StubProvider("openai", chat_results=[RuntimeError("openai down")])
    deepseek = StubProvider("deepseek", chat_results=[RuntimeError("deepseek down")])
    factory = make_factory({"openai": openai, "deepseek": deepseek})

    with pytest.raises(ProviderUnavailableError, match="所有 Provider 均不可用"):
        await factory.chat_with_fallback([{"role": "user", "content": "hello"}])


@pytest.mark.asyncio
async def test_react_agent_uses_factory_fallback() -> None:
    openai = StubProvider("openai", chat_results=[RuntimeError("quota exceeded")])
    deepseek = StubProvider(
        "deepseek",
        chat_results=[{"content": "answer from deepseek", "tool_calls": []}],
    )
    factory = make_factory({"openai": openai, "deepseek": deepseek})
    agent = ReActAgent(factory, tool_registry=ToolRegistry())

    result = await agent.run("hello")

    assert result.answer == "answer from deepseek"
    assert openai.chat_calls == deepseek.chat_calls == 1


@pytest.mark.asyncio
async def test_react_agent_allows_factory_to_probe_recovering_provider() -> None:
    openai = StubProvider("openai", chat_results=[{"content": "recovered", "tool_calls": []}])
    factory = make_factory({"openai": openai})
    openai.health = ProviderHealth.UNHEALTHY
    openai.consecutive_failures = 3
    openai.recovery_timeout = 0

    result = await ReActAgent(factory, tool_registry=ToolRegistry()).run("hello")

    assert result.answer == "recovered"
    assert result.status == "completed"
