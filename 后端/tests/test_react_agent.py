"""ReAct Agent 核心工具执行链路测试。"""

from __future__ import annotations

import copy
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.core.agent.react_agent import ReActAgent
from src.core.tools.registry import Tool, ToolRegistry, ToolSpec


class StubProvider:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = iter(responses)
        self.calls: list[dict[str, Any]] = []

    async def chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"messages": copy.deepcopy(messages), **kwargs})
        return next(self._responses)


class StubProviderFactory:
    def __init__(self, provider: StubProvider) -> None:
        self.provider = provider

    def get_provider(self) -> StubProvider:
        return self.provider


def make_tool_registry(name: str, fn: Any) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        Tool(
            name=name,
            description="test tool",
            fn=fn,
            spec=ToolSpec(
                name=name,
                description="test tool",
                parameters={"type": "object", "properties": {}},
            ),
        )
    )
    return registry


@pytest.mark.asyncio
async def test_agent_returns_direct_answer_without_tools() -> None:
    provider = StubProvider(
        [{"content": "direct answer", "tool_calls": [], "input_tokens": 4, "output_tokens": 2}]
    )
    agent = ReActAgent(StubProviderFactory(provider), tool_registry=ToolRegistry())

    result = await agent.run("question")

    assert result.answer == "direct answer"
    assert result.steps == []
    assert result.total_tokens == 6
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_agent_executes_tool_then_returns_final_answer() -> None:
    tool_fn = AsyncMock(return_value="weather is sunny")
    provider = StubProvider(
        [
            {
                "content": "checking weather",
                "tool_calls": [{"id": "call-1", "name": "weather", "args": {"city": "Shanghai"}}],
            },
            {"content": "It is sunny.", "tool_calls": []},
        ]
    )
    agent = ReActAgent(
        StubProviderFactory(provider),
        tool_registry=make_tool_registry("weather", tool_fn),
    )

    result = await agent.run("How is the weather?")

    tool_fn.assert_awaited_once_with(city="Shanghai")
    assert result.answer == "It is sunny."
    assert len(result.steps) == 1
    assert result.steps[0].observation == "weather is sunny"
    assert provider.calls[1]["messages"][-1]["role"] == "tool"
    assert provider.calls[1]["messages"][-1]["content"] == "weather is sunny"


@pytest.mark.asyncio
async def test_agent_reports_tool_failure_and_continues() -> None:
    tool_fn = AsyncMock(side_effect=RuntimeError("backend unavailable"))
    provider = StubProvider(
        [
            {
                "content": "calling service",
                "tool_calls": [{"name": "unstable", "args": {}}],
            },
            {"content": "I used a fallback.", "tool_calls": []},
        ]
    )
    agent = ReActAgent(
        StubProviderFactory(provider),
        tool_registry=make_tool_registry("unstable", tool_fn),
    )

    result = await agent.run("Run the service")

    assert result.answer == "I used a fallback."
    assert len(result.steps) == 1
    assert "RuntimeError" in result.steps[0].observation
    assert "backend unavailable" in provider.calls[1]["messages"][-1]["content"]


@pytest.mark.asyncio
async def test_agent_stops_at_max_iterations() -> None:
    tool_fn = AsyncMock(return_value="still running")
    responses = [
        {
            "content": f"iteration {index}",
            "tool_calls": [{"name": "repeat", "args": {"index": index}}],
        }
        for index in range(3)
    ]
    provider = StubProvider(responses)
    agent = ReActAgent(
        StubProviderFactory(provider),
        tool_registry=make_tool_registry("repeat", tool_fn),
        max_iterations=3,
    )

    result = await agent.run("keep going")

    assert len(provider.calls) == 3
    assert len(result.steps) == 3
    assert tool_fn.await_count == 3
    assert result.answer == "iteration 2"
    assert result.status == "max_iterations_exceeded"
    assert result.error == "ReAct 达到最大迭代次数"


@pytest.mark.asyncio
async def test_agent_rejects_empty_final_response() -> None:
    provider = StubProvider([{"content": "", "tool_calls": []}])
    agent = ReActAgent(
        StubProviderFactory(provider),
        tool_registry=ToolRegistry(),
    )

    result = await agent.run("hello")

    assert result.status == "failed"
    assert result.error == "LLM 返回空答案"
