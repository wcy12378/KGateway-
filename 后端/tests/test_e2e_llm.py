"""真实 DeepSeek LLM 端到端集成测试。"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio

import src.core.tools.builtin  # noqa: F401 - 导入时注册内置工具
from src.config import GatewayConfig
from src.core.agent.react_agent import ReActAgent
from src.core.providers.factory import ProviderFactory
from src.core.tools.registry import ToolRegistry, get_registry


pytestmark = pytest.mark.skipif(
    not os.getenv("KAGENT_DEEPSEEK_API_KEY"),
    reason="需要配置 KAGENT_DEEPSEEK_API_KEY 才能运行",
)


class _DeterministicFactory:
    """测试适配器：保留真实 ProviderFactory，仅固定生成参数。"""

    def __init__(self, factory: ProviderFactory) -> None:
        self._factory = factory

    async def chat_with_fallback(self, messages: list[dict], **kwargs: Any) -> dict:
        kwargs.setdefault("temperature", 0)
        kwargs.setdefault("max_tokens", 256)
        return await self._factory.chat_with_fallback(messages, preferred="deepseek", **kwargs)


@pytest_asyncio.fixture
async def deepseek_factory() -> AsyncIterator[ProviderFactory]:
    """创建独立 Factory，并确保持久化 HTTP 客户端被关闭。"""
    factory = ProviderFactory()
    factory.init(GatewayConfig())
    assert factory.get_provider("deepseek") is not None
    try:
        yield factory
    finally:
        await factory.close()


def _tool_names(response: dict) -> list[str]:
    names: list[str] = []
    for call in response.get("tool_calls") or []:
        function = call.get("function") if isinstance(call, dict) else None
        if isinstance(function, dict) and function.get("name"):
            names.append(str(function["name"]))
        elif isinstance(call, dict) and call.get("name"):
            names.append(str(call["name"]))
    return names


@pytest.mark.asyncio
async def test_agent_calculator_tool_calling(deepseek_factory: ProviderFactory) -> None:
    """Agent 应真实调用 calculator，并基于工具结果生成最终答案。"""
    registry = ToolRegistry()
    calculator = get_registry().get("calculator")
    assert calculator is not None
    registry.register(calculator)
    agent = ReActAgent(
        _DeterministicFactory(deepseek_factory),
        tool_registry=registry,
        max_iterations=3,
    )

    result = await asyncio.wait_for(
        agent.run(
            "必须调用 calculator 工具计算 (12345 * 6789) + 17，随后只根据工具结果回答。",
            system_prompt="你是工具调用测试助手。计算题必须调用提供的 calculator 工具，不能心算。",
            persist_memory=False,
        ),
        timeout=60,
    )

    assert result.status == "completed", result.error
    assert any(step.action == "calculator" for step in result.steps)
    assert any("83810222" in step.observation.replace(",", "") for step in result.steps)
    assert "83810222" in result.answer.replace(",", "").replace(" ", "")


@pytest.mark.asyncio
async def test_agent_query_knowledge_tool_calling(deepseek_factory: ProviderFactory) -> None:
    """模型收到企业知识问题时，应返回 query_knowledge 工具调用。"""
    provider = deepseek_factory.get_provider("deepseek")
    query_knowledge = get_registry().get("query_knowledge")
    assert provider is not None
    assert query_knowledge is not None

    response = await asyncio.wait_for(
        provider.chat(
            [
                {
                    "role": "system",
                    "content": "企业内部知识问题必须调用提供的 query_knowledge 工具，不得直接回答。",
                },
                {"role": "user", "content": "请查询公司差旅报销制度中的住宿标准。"},
            ],
            temperature=0,
            max_tokens=128,
            tools=[query_knowledge.to_openai_tool()],
        ),
        timeout=60,
    )

    assert _tool_names(response) == ["query_knowledge"]


@pytest.mark.asyncio
async def test_agent_direct_answer_without_tools(deepseek_factory: ProviderFactory) -> None:
    """简单寒暄应直接回答，不应调用任何工具。"""
    provider = deepseek_factory.get_provider("deepseek")
    assert provider is not None

    response = await asyncio.wait_for(
        provider.chat(
            [
                {
                    "role": "system",
                    "content": "简单寒暄直接简短回答；只有确实需要时才调用工具。",
                },
                {"role": "user", "content": "你好，请用一句话回复。"},
            ],
            temperature=0,
            max_tokens=64,
            tools=get_registry().to_openai_tools(),
        ),
        timeout=60,
    )

    assert not response.get("tool_calls")
    assert str(response.get("content") or "").strip()
