"""Prompt 模板版本管理与运行时切换测试。"""

from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from src.api import routes
from src.core.agent.react_agent import ReActAgent
from src.core.prompts.registry import (
    PromptRegistry,
    PromptRenderError,
    PromptTemplate,
    get_registry,
)
from src.core.tools.registry import ToolRegistry


def test_prompt_render_is_strict_and_deterministic() -> None:
    template = PromptTemplate(
        name="greeting",
        version="1.2.0",
        template="Hello {name}, tools: {tools}",
    )

    assert template.render(name="World", tools="none") == "Hello World, tools: none"
    assert template.variables == ("name", "tools")
    assert len(template.content_hash) == 12
    with pytest.raises(PromptRenderError, match="tools"):
        template.render(name="World")


def test_registry_rejects_silent_version_overwrite() -> None:
    registry = PromptRegistry()
    registry.register(PromptTemplate("same", "1.0.0", "first"), activate=True)

    with pytest.raises(ValueError, match="不同内容"):
        registry.register(PromptTemplate("same", "1.0.0", "second"))


class CapturingProvider:
    def __init__(self) -> None:
        self.system_prompts: list[str] = []

    async def chat(self, messages: list[dict[str, Any]], **_: Any) -> dict[str, Any]:
        copied = copy.deepcopy(messages)
        self.system_prompts.append(str(copied[0]["content"]))
        return {"content": "ok", "tool_calls": []}


class ProviderFactory:
    def __init__(self, provider: CapturingProvider) -> None:
        self.provider = provider

    def get_provider(self) -> CapturingProvider:
        return self.provider


@pytest.mark.asyncio
async def test_existing_agent_observes_runtime_version_switch() -> None:
    registry = PromptRegistry()
    registry.register(
        PromptTemplate("switchable", "1.0.0", "VERSION-1 {request_context}"),
        activate=True,
    )
    registry.register(PromptTemplate("switchable", "2.0.0", "VERSION-2 {request_context}"))
    provider = CapturingProvider()
    agent = ReActAgent(
        ProviderFactory(provider),
        tool_registry=ToolRegistry(),
        prompt_registry=registry,
        prompt_name="switchable",
    )

    await agent.run("first")
    registry.activate("switchable", "2.0.0")
    await agent.run("second")

    assert provider.system_prompts[0].startswith("VERSION-1")
    assert provider.system_prompts[1].startswith("VERSION-2")


def test_default_manifest_loads_all_agent_prompts() -> None:
    names = {item["name"] for item in get_registry().list()}

    assert {
        "react_default",
        "research_retriever",
        "research_writer",
        "enterprise_specialist",
        "math_specialist",
        "general_specialist",
        "solution_analyst",
        "risk_reviewer",
        "review_synthesizer",
    } <= names


@pytest.mark.asyncio
async def test_prompt_activation_endpoint_requires_api_key_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = PromptRegistry()
    registry.register(PromptTemplate("managed", "1.0.0", "one"), activate=True)
    registry.register(PromptTemplate("managed", "2.0.0", "two"))
    app = SimpleNamespace(state=SimpleNamespace(prompt_registry=registry))
    jwt_request = SimpleNamespace(app=app, state=SimpleNamespace(auth_method="jwt"))
    with pytest.raises(HTTPException) as exc_info:
        await routes.gateway_prompt_activate("managed", "2.0.0", jwt_request)
    assert exc_info.value.status_code == 403
    assert registry.active_version("managed") == "1.0.0"

    api_key_request = SimpleNamespace(app=app, state=SimpleNamespace(auth_method="api_key"))
    response = await routes.gateway_prompt_activate("managed", "2.0.0", api_key_request)

    assert response["active_version"] == "2.0.0"
    assert registry.active_version("managed") == "2.0.0"
