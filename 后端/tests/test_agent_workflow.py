"""多 Agent 工作流核心行为测试。"""

from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any, Awaitable, Callable
from unittest.mock import AsyncMock

import pytest

from src.api import routes
from src.core.agent.workflow import (
    AgentSpec,
    RoutingRule,
    WorkflowEngine,
    WorkflowMode,
    WorkflowResult,
)
from src.core.prompts.registry import PromptRegistry, PromptTemplate
from src.core.schemas import GatewayWorkflowRequest
from src.core.tools.registry import Tool, ToolRegistry, ToolSpec

Handler = Callable[[str, str, list[dict[str, Any]]], Awaitable[dict[str, Any]]]
TEST_PROMPTS = PromptRegistry()


class PromptProvider:
    def __init__(self, handler: Handler) -> None:
        self.handler = handler
        self.calls: list[dict[str, Any]] = []

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        self.calls.append({"messages": copy.deepcopy(messages), "tools": copy.deepcopy(tools)})
        return await self.handler(
            str(messages[0]["content"]),
            str(messages[-1]["content"]),
            tools or [],
        )


class ProviderFactory:
    def __init__(self, provider: PromptProvider) -> None:
        self.provider = provider

    def get_provider(self) -> PromptProvider:
        return self.provider


class FakeMemoryManager:
    def __init__(self) -> None:
        self.remembered: list[dict[str, str]] = []

    async def get_relevant_memories(self, **_: Any) -> list[Any]:
        return []

    @staticmethod
    def format_memories_for_prompt(_: list[Any]) -> str:
        return ""

    async def remember_exchange(self, **kwargs: str) -> int:
        self.remembered.append(kwargs)
        return 1


def spec(name: str, prompt: str, *, tools: tuple[str, ...] = ()) -> AgentSpec:
    prompt_name = f"test_{name}"
    TEST_PROMPTS.register(
        PromptTemplate(
            name=prompt_name,
            version="1.0.0",
            template=prompt,
            description="test prompt",
        ),
        activate=True,
    )
    return AgentSpec(
        name=name,
        description=f"{name} description",
        prompt_name=prompt_name,
        tool_names=tools,
        max_iterations=2,
    )


@pytest.mark.asyncio
async def test_sequential_handoff_and_single_memory_write() -> None:
    async def handler(system: str, user: str, _: list[dict[str, Any]]) -> dict[str, Any]:
        if "RETRIEVER" in system:
            return {"content": "evidence-1", "tool_calls": [], "input_tokens": 1, "output_tokens": 2}
        assert "原始问题" in user
        assert "evidence-1" in user
        return {"content": "final-answer", "tool_calls": [], "input_tokens": 2, "output_tokens": 3}

    memory = FakeMemoryManager()
    engine = WorkflowEngine(
        ProviderFactory(PromptProvider(handler)),
        tool_registry=ToolRegistry(),
        memory_manager=memory,
        prompt_registry=TEST_PROMPTS,
    )
    engine.register_workflow(
        name="seq",
        mode=WorkflowMode.SEQUENTIAL,
        agents=(spec("retriever", "RETRIEVER"), spec("writer", "WRITER")),
    )

    result = await engine.run(
        "seq",
        "original-question",
        context={"user_id": "user-a", "tenant_id": "tenant-a"},
    )

    assert result.status == "completed"
    assert result.final_answer == "final-answer"
    assert [step.agent_name for step in result.steps] == ["retriever", "writer"]
    assert result.steps[0].input_text == "original-question"
    assert "evidence-1" in result.steps[1].input_text
    assert result.total_tokens == 8
    assert len(memory.remembered) == 1
    assert memory.remembered[0]["answer"] == "final-answer"


@pytest.mark.asyncio
async def test_routing_uses_explicit_rules_and_fallback() -> None:
    async def handler(system: str, _: str, __: list[dict[str, Any]]) -> dict[str, Any]:
        answer = "math" if "MATH" in system else "general"
        return {"content": answer, "tool_calls": []}

    engine = WorkflowEngine(
        ProviderFactory(PromptProvider(handler)),
        tool_registry=ToolRegistry(),
        prompt_registry=TEST_PROMPTS,
    )
    engine.register_workflow(
        name="route",
        mode=WorkflowMode.ROUTING,
        agents=(spec("math", "MATH"), spec("general", "GENERAL")),
        routing_rules=(RoutingRule("math", ("计算", "+")),),
        fallback_agent="general",
    )

    math_result = await engine.run("route", "请计算 1+1")
    general_result = await engine.run("route", "你好")

    assert math_result.steps[0].agent_name == "math"
    assert math_result.final_answer == "math"
    assert general_result.steps[0].agent_name == "general"
    assert general_result.final_answer == "general"


@pytest.mark.asyncio
async def test_parallel_uses_synthesizer_and_sums_all_tokens() -> None:
    async def handler(system: str, user: str, _: list[dict[str, Any]]) -> dict[str, Any]:
        if "SYNTH" in system:
            assert "answer-a" in user and "answer-b" in user
            return {"content": "merged-answer", "tool_calls": [], "input_tokens": 2, "output_tokens": 2}
        answer = "answer-a" if "WORKER-A" in system else "answer-b"
        return {"content": answer, "tool_calls": [], "input_tokens": 1, "output_tokens": 1}

    engine = WorkflowEngine(
        ProviderFactory(PromptProvider(handler)),
        tool_registry=ToolRegistry(),
        prompt_registry=TEST_PROMPTS,
        max_parallelism=2,
    )
    engine.register_workflow(
        name="parallel",
        mode=WorkflowMode.PARALLEL,
        agents=(spec("worker-a", "WORKER-A"), spec("worker-b", "WORKER-B")),
        synthesizer=spec("synth", "SYNTH"),
    )

    result = await engine.run("parallel", "question")

    assert result.status == "completed"
    assert result.final_answer == "merged-answer"
    assert [step.agent_name for step in result.steps] == ["worker-a", "worker-b", "synth"]
    assert result.total_tokens == 8


@pytest.mark.asyncio
async def test_parallel_keeps_partial_results_when_one_agent_fails() -> None:
    async def handler(system: str, _: str, __: list[dict[str, Any]]) -> dict[str, Any]:
        if "FAIL" in system:
            raise RuntimeError("upstream failed")
        return {"content": "surviving-answer", "tool_calls": [], "input_tokens": 1}

    engine = WorkflowEngine(
        ProviderFactory(PromptProvider(handler)),
        tool_registry=ToolRegistry(),
        prompt_registry=TEST_PROMPTS,
    )
    engine.register_workflow(
        name="partial",
        mode=WorkflowMode.PARALLEL,
        agents=(spec("ok", "OK"), spec("bad", "FAIL")),
    )

    result = await engine.run("partial", "question")

    assert result.status == "partial"
    assert "surviving-answer" in result.final_answer
    assert result.steps[1].status == "failed"
    assert "RuntimeError" in (result.steps[1].error or "")


@pytest.mark.asyncio
async def test_tool_allowlist_blocks_unregistered_tool_execution() -> None:
    allowed = AsyncMock(return_value="allowed")
    blocked = AsyncMock(return_value="blocked")
    registry = ToolRegistry()
    for name, fn in (("allowed", allowed), ("blocked", blocked)):
        registry.register(
            Tool(
                name=name,
                description=name,
                fn=fn,
                spec=ToolSpec(name=name, description=name, parameters={"type": "object"}),
            )
        )

    calls = 0

    async def handler(_: str, __: str, tools: list[dict[str, Any]]) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        expected_tools = ["allowed"] if calls == 1 else []
        assert [tool["function"]["name"] for tool in tools] == expected_tools
        if calls == 1:
            return {"content": "", "tool_calls": [{"name": "blocked", "args": {}}]}
        return {"content": "handled", "tool_calls": []}

    engine = WorkflowEngine(
        ProviderFactory(PromptProvider(handler)),
        tool_registry=registry,
        prompt_registry=TEST_PROMPTS,
    )
    engine.register_workflow(
        name="allowlist",
        mode=WorkflowMode.SEQUENTIAL,
        agents=(spec("restricted", "RESTRICTED", tools=("allowed",)),),
    )

    result = await engine.run("allowlist", "question")

    assert result.final_answer == "handled"
    assert result.steps[0].output is not None
    assert result.steps[0].output.steps[0].observation == "工具不存在: blocked"
    blocked.assert_not_awaited()


@pytest.mark.asyncio
async def test_workflow_api_overrides_untrusted_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class FakeEngine:
        async def run(self, name: str, question: str, context: dict[str, Any]) -> WorkflowResult:
            captured.update(name=name, question=question, context=context)
            return WorkflowResult(
                workflow_name=name,
                mode=WorkflowMode.ROUTING,
                final_answer="ok",
            )

    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(workflow_engine=FakeEngine())),
        state=SimpleNamespace(
            user=SimpleNamespace(user_id="trusted-user", tenant_id="trusted-tenant", department="hr")
        )
    )
    body = GatewayWorkflowRequest(
        workflow_name="route",
        user_id="attacker",
        tenant_id="attacker-tenant",
        department="general",
        question="question",
    )

    response = await routes.gateway_workflow(body, request)

    assert response.final_answer == "ok"
    assert captured["context"]["user_id"] == "trusted-user"
    assert captured["context"]["tenant_id"] == "trusted-tenant"
    assert captured["context"]["department"] == "hr"
