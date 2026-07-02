"""Phase 0 审查发现问题的回归测试。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import jwt
import pytest

from src.api.auth import create_token, verify_token
from src.config import config
from src.core.agent.react_agent import ReActAgent, _normalize_tool_call
from src.core.providers.factory import ProviderFactory
from src.core.providers.gemini import GeminiProvider
from src.core.tools.registry import Tool, ToolRegistry, ToolSpec


def test_provider_factory_instances_do_not_share_mutable_config() -> None:
    """不同应用或测试中的工厂不能互相重置 Provider 缓存。"""
    assert ProviderFactory() is not ProviderFactory()


def test_gemini_api_key_is_not_embedded_in_url() -> None:
    """Gemini 密钥应放在请求头，避免进入代理访问日志。"""
    provider = GeminiProvider(SimpleNamespace(gemini_api_key="secret-key", gemini_model="gemini-test"))
    assert "secret-key" not in provider._url("gemini-test", stream=False)
    assert provider._headers() == {"x-goog-api-key": "secret-key"}


def test_normalize_gemini_and_openai_tool_calls() -> None:
    """两种 Provider 的工具调用都应归一化为 OpenAI 消息格式。"""
    gemini, gemini_name, gemini_args = _normalize_tool_call(
        {"name": "calculator", "args": {"expression": "1+1"}},
        0,
        call_id_prefix="call_2",
    )
    openai, openai_name, openai_args = _normalize_tool_call(
        {
            "id": "provider-call-id",
            "function": {"name": "calculator", "arguments": '{"expression":"2+2"}'},
        },
        0,
    )
    assert gemini["id"] == "call_2_0"
    assert gemini_name == openai_name == "calculator"
    assert gemini_args == {"expression": "1+1"}
    assert openai_args == {"expression": "2+2"}
    assert openai["id"] == "provider-call-id"


@pytest.mark.asyncio
async def test_react_agent_overrides_model_supplied_tenant_scope() -> None:
    """知识库工具的租户与部门必须来自认证上下文，而不是模型参数。"""
    captured: dict[str, str] = {}

    async def query_knowledge(query: str, tenant_id: str, department: str) -> str:
        captured.update(query=query, tenant_id=tenant_id, department=department)
        return "trusted result"

    registry = ToolRegistry()
    spec = ToolSpec(
        name="query_knowledge",
        description="test",
        parameters={"type": "object", "properties": {}},
    )
    registry.register(Tool("query_knowledge", "test", query_knowledge, spec))

    class FakeProvider:
        calls = 0

        async def chat(self, messages: list[dict], **_: Any) -> dict:
            self.calls += 1
            if self.calls == 1:
                return {
                    "content": "search",
                    "tool_calls": [
                        {
                            "name": "query_knowledge",
                            "args": {
                                "query": "policy",
                                "tenant_id": "attacker-tenant",
                                "department": "legal",
                            },
                        }
                    ],
                }
            return {"content": "done", "tool_calls": []}

    provider = FakeProvider()
    factory = SimpleNamespace(get_provider=lambda: provider)
    result = await ReActAgent(factory, registry, max_iterations=3).run(
        "question",
        context={"tenant_id": "trusted-tenant", "department": "engineering"},
    )

    assert result.answer == "done"
    assert captured == {
        "query": "policy",
        "tenant_id": "trusted-tenant",
        "department": "engineering",
    }


@pytest.mark.asyncio
async def test_react_agent_overrides_scope_for_every_scoped_tool() -> None:
    captured: dict[str, str] = {}

    async def enterprise_action(query: str, tenant_id: str, user_id: str) -> str:
        captured.update(query=query, tenant_id=tenant_id, user_id=user_id)
        return "done"

    registry = ToolRegistry()
    spec = ToolSpec(
        name="enterprise_action",
        description="test",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "tenant_id": {"type": "string"},
                "user_id": {"type": "string"},
            },
            "required": ["query", "tenant_id", "user_id"],
        },
    )
    registry.register(Tool("enterprise_action", "test", enterprise_action, spec))

    class FakeProvider:
        calls = 0

        async def chat(self, messages: list[dict], **_: Any) -> dict:
            self.calls += 1
            if self.calls == 1:
                return {
                    "content": "run",
                    "tool_calls": [{
                        "name": "enterprise_action",
                        "args": {
                            "query": "policy",
                            "tenant_id": "attacker",
                            "user_id": "attacker",
                        },
                    }],
                }
            return {"content": "done", "tool_calls": []}

    provider = FakeProvider()
    result = await ReActAgent(SimpleNamespace(get_provider=lambda: provider), registry).run(
        "question",
        context={"tenant_id": "trusted-tenant", "user_id": "trusted-user"},
    )

    assert result.answer == "done"
    assert captured == {
        "query": "policy",
        "tenant_id": "trusted-tenant",
        "user_id": "trusted-user",
    }


def test_jwt_requires_identity_claims() -> None:
    """签名正确但缺少身份声明的 token 也必须拒绝。"""
    incomplete = jwt.encode({"exp": 4_102_444_800}, config.jwt_secret, algorithm=config.jwt_algorithm)
    with pytest.raises(Exception):
        verify_token(incomplete)


def test_jwt_round_trip() -> None:
    token = create_token("user-1", "tenant-1", "engineering", expires_in=60)
    payload = verify_token(token)
    assert (payload.user_id, payload.tenant_id, payload.department) == (
        "user-1",
        "tenant-1",
        "engineering",
    )
