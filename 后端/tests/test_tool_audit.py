"""工具调用审计、脱敏和查询隔离测试。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.api import routes
from src.core.agent.react_agent import ReActAgent
from src.core.audit import AuditEntry, AuditLogger
from src.core.tools.registry import Tool, ToolRegistry, ToolSpec


def test_audit_recursively_redacts_params_and_result() -> None:
    audit = AuditLogger(max_entries=10)
    audit.record(
        AuditEntry(
            tenant_id="tenant-a",
            tool_name="external_api",
            tool_params={
                "query": "safe",
                "password": "super-secret",
                "nested": {"apiKey": "abcdef123456", "monkey": "visible"},
            },
            result_status="success",
            result_summary='Bearer abc.def token="result-secret" normal output',
        )
    )

    entry = audit.query(tenant_id="tenant-a")["entries"][0]
    assert entry["tool_params"]["query"] == "safe"
    assert entry["tool_params"]["password"] == "su****et"
    assert entry["tool_params"]["nested"]["apiKey"] == "ab****56"
    assert entry["tool_params"]["nested"]["monkey"] == "visible"
    assert "abc.def" not in entry["result_summary"]
    assert "result-secret" not in entry["result_summary"]


def test_audit_ring_buffer_and_newest_first_query() -> None:
    audit = AuditLogger(max_entries=2)
    audit.record(AuditEntry(tool_name="first"))
    audit.record(AuditEntry(tool_name="second", result_status="success"))
    audit.record(AuditEntry(tool_name="third", result_status="success"))

    result = audit.query(result_status="success")

    assert result["total"] == 2
    assert [entry["tool_name"] for entry in result["entries"]] == ["third", "second"]


class StubProvider:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = iter(responses)

    async def chat(self, *_: Any, **__: Any) -> dict[str, Any]:
        return next(self.responses)


class ProviderFactory:
    def __init__(self, provider: StubProvider) -> None:
        self.provider = provider

    def get_provider(self) -> StubProvider:
        return self.provider


def make_tool_registry(fn: Any) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="query_knowledge",
            description="knowledge",
            fn=fn,
            spec=ToolSpec(
                name="query_knowledge",
                description="knowledge",
                parameters={"type": "object", "properties": {}},
            ),
        )
    )
    return registry


@pytest.mark.asyncio
async def test_react_audits_effective_scope_success_and_failure() -> None:
    query_tool = AsyncMock(return_value="trusted-result")
    provider = StubProvider(
        [
            {
                "content": "use tools",
                "tool_calls": [
                    {
                        "id": "call-good",
                        "name": "query_knowledge",
                        "args": {
                            "query": "policy",
                            "tenant_id": "attacker-tenant",
                            "department": "finance",
                        },
                    },
                    {
                        "id": "call-bad",
                        "name": "missing_tool",
                        "args": {"token": "secret-token"},
                    },
                ],
            },
            {"content": "final", "tool_calls": []},
        ]
    )
    audit = AuditLogger()
    agent = ReActAgent(
        ProviderFactory(provider),
        tool_registry=make_tool_registry(query_tool),
        audit_logger=audit,
    )

    result = await agent.run(
        "question",
        context={
            "user_id": "user-a",
            "tenant_id": "tenant-a",
            "department": "hr",
            "session_id": "session-a",
            "trace_id": "trace-a",
            "workflow_name": "research",
            "agent_name": "retriever",
        },
    )

    assert result.answer == "final"
    query_tool.assert_awaited_once_with(query="policy", tenant_id="tenant-a", department="hr")
    entries = {entry["tool_name"]: entry for entry in audit.query()["entries"]}
    success = entries["query_knowledge"]
    assert success["result_status"] == "success"
    assert success["tool_params"]["tenant_id"] == "tenant-a"
    assert success["user_id"] == "user-a"
    assert success["trace_id"] == "trace-a"
    assert success["workflow_name"] == "research"
    assert success["agent_name"] == "retriever"
    failure = entries["missing_tool"]
    assert failure["result_status"] == "failure"
    assert failure["tool_params"]["token"] == "se****en"


@pytest.mark.asyncio
async def test_audit_failure_does_not_break_tool_execution() -> None:
    class BrokenAuditLogger:
        def record(self, _: AuditEntry) -> None:
            raise RuntimeError("audit unavailable")

    tool_fn = AsyncMock(return_value="tool-result")
    provider = StubProvider(
        [
            {"content": "call", "tool_calls": [{"name": "query_knowledge", "args": {"query": "q"}}]},
            {"content": "final-answer", "tool_calls": []},
        ]
    )
    agent = ReActAgent(
        ProviderFactory(provider),
        tool_registry=make_tool_registry(tool_fn),
        audit_logger=BrokenAuditLogger(),  # type: ignore[arg-type]
    )

    result = await agent.run("question")

    assert result.answer == "final-answer"
    tool_fn.assert_awaited_once()


@pytest.mark.asyncio
async def test_audit_query_is_scoped_for_jwt_and_global_for_api_key() -> None:
    audit = AuditLogger()
    audit.record(AuditEntry(tenant_id="tenant-a", user_id="user-a", tool_name="one"))
    audit.record(AuditEntry(tenant_id="tenant-a", user_id="user-b", tool_name="two"))
    audit.record(AuditEntry(tenant_id="tenant-b", user_id="user-c", tool_name="three"))
    app = SimpleNamespace(state=SimpleNamespace(audit_logger=audit))

    jwt_request = SimpleNamespace(
        app=app,
        state=SimpleNamespace(
            auth_method="jwt",
            user=SimpleNamespace(user_id="user-a", tenant_id="tenant-a"),
        ),
    )
    jwt_result = await routes.gateway_audit(
        jwt_request,
        limit=50,
        offset=0,
        tool=None,
        result_status=None,
        trace_id=None,
        tenant_id="tenant-b",
        user_id="user-c",
    )
    assert jwt_result["total"] == 1
    assert jwt_result["entries"][0]["user_id"] == "user-a"

    api_key_request = SimpleNamespace(
        app=app,
        state=SimpleNamespace(
            auth_method="api_key",
            user=SimpleNamespace(user_id="api_key_client", tenant_id="default_tenant"),
        ),
    )
    api_key_result = await routes.gateway_audit(
        api_key_request,
        limit=50,
        offset=0,
        tool=None,
        result_status=None,
        trace_id=None,
        tenant_id=None,
        user_id=None,
    )
    assert api_key_result["total"] == 3
