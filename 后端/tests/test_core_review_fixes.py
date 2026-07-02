"""Core 模块代码审查缺陷的回归测试。"""

from __future__ import annotations

import asyncio
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.protection import CircuitBreaker, CircuitState
from src.core.cache import SemanticCacheManager
from src.core.fusion import reciprocal_rank_fusion
from src.core.mcp.client import MCPClient
from src.core.providers.base import ProviderHealth
from src.core.providers.factory import ProviderFactory
from src.core.providers.gemini import GeminiProvider
from src.core.providers.openai import OpenAIProvider
from src.core.tools.builtin import _validate_expression
from src.core.tools.registry import Tool, ToolRegistry, ToolSpec, get_registry, tool
from src.core.router import BASIC_MODEL, ModelRouter
from src.core.schemas import GatewayRequest


def test_circuit_breaker_closes_after_configured_half_open_successes() -> None:
    breaker = CircuitBreaker(
        failure_threshold=1,
        recovery_timeout=0,
        half_open_max_calls=3,
    )
    breaker.record_failure(RuntimeError("down"))

    for _ in range(3):
        assert breaker.allow_request() is True
        breaker.record_success()

    assert breaker.state is CircuitState.CLOSED


def test_circuit_breaker_success_resets_consecutive_failures() -> None:
    breaker = CircuitBreaker(failure_threshold=3)

    breaker.record_failure(RuntimeError("one"))
    breaker.record_failure(RuntimeError("two"))
    breaker.record_success()
    breaker.record_failure(RuntimeError("one"))
    breaker.record_failure(RuntimeError("two"))

    assert breaker.state is CircuitState.CLOSED
    assert breaker.stats()["failure_count"] == 2


@pytest.mark.parametrize(
    "expression",
    [
        "pow(2, 1000001)",
        "[1] * 1000001",
    ],
)
def test_calculator_rejects_resource_exhausting_expressions(expression: str) -> None:
    with pytest.raises(ValueError, match="规模"):
        _validate_expression(expression)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_class", "module_name", "response_data"),
    [
        (
            OpenAIProvider,
            "src.core.providers.openai.httpx.AsyncClient",
            {"choices": [{"message": {"content": "ok"}}], "usage": {}},
        ),
        (
            GeminiProvider,
            "src.core.providers.gemini.httpx.AsyncClient",
            {"candidates": [{"content": {"parts": [{"text": "ok"}]}}], "usageMetadata": {}},
        ),
    ],
)
async def test_provider_chat_reuses_base_http_client(
    provider_class: type,
    module_name: str,
    response_data: dict,
) -> None:
    config = SimpleNamespace(
        openai_api_key="key",
        openai_model="openai-model",
        openai_api_url="https://example.invalid/openai",
        gemini_api_key="key",
        gemini_model="gemini-model",
    )
    provider = provider_class(config)
    response = MagicMock()
    response.json.return_value = response_data
    response.raise_for_status.return_value = None
    client = MagicMock(is_closed=False)
    client.post = AsyncMock(return_value=response)
    provider._client = client

    with patch(module_name, side_effect=AssertionError("不应创建临时客户端")):
        result = await provider.chat([{"role": "user", "content": "hello"}])

    assert result["content"] == "ok"
    client.post.assert_awaited_once()


def test_provider_recovery_allows_only_one_probe() -> None:
    config = SimpleNamespace(
        kagent_llm_provider="openai",
        provider_routing_strategy="priority",
        openai_api_key="key",
        deepseek_api_key="",
        gemini_api_key="",
        openai_model="model",
        openai_api_url="https://example.invalid",
    )
    factory = ProviderFactory()
    factory.init(config)
    provider = factory.get_all_providers()[0]
    provider.health = ProviderHealth.UNHEALTHY
    provider.consecutive_failures = 3
    provider.recovery_timeout = 0

    assert factory.get_provider_candidates(reserve_recovery_probe=True) == [provider]
    assert factory.get_provider_candidates(reserve_recovery_probe=True) == []

    factory.record_success(provider.name, 1)
    assert factory.get_provider_candidates() == [provider]


def test_tool_registry_rejects_duplicate_names() -> None:
    registry = ToolRegistry()
    spec = ToolSpec("duplicate", "test", {"type": "object", "properties": {}})

    registry.register(Tool("duplicate", "first", AsyncMock(), spec))
    with pytest.raises(ValueError, match="已注册"):
        registry.register(Tool("duplicate", "second", AsyncMock(), spec))


@pytest.mark.asyncio
async def test_mcp_tool_discovery_reads_all_pages() -> None:
    first_tool = SimpleNamespace(name="first", description="", inputSchema={})
    second_tool = SimpleNamespace(name="second", description="", inputSchema={})
    session = AsyncMock()
    session.list_tools.side_effect = [
        SimpleNamespace(tools=[first_tool], nextCursor="page-2"),
        SimpleNamespace(tools=[second_tool], nextCursor=None),
    ]
    client = MCPClient("test", "unused")
    client._session = session

    tools = await client.list_tools()

    assert [tool.name for tool in tools] == ["first", "second"]
    assert session.list_tools.await_args_list[1].kwargs == {"cursor": "page-2"}


def test_rrf_ranks_each_input_by_its_score() -> None:
    result = reciprocal_rank_fusion(
        dense_results=[
            {"doc_id": "low", "vector_score": 0.1},
            {"doc_id": "high", "vector_score": 0.9},
        ],
        sparse_results=[],
    )

    assert [document.doc_id for document in result] == ["high", "low"]


@pytest.mark.asyncio
async def test_semantic_cache_rejects_wrong_vector_dimension_before_redis() -> None:
    cache = SemanticCacheManager(vector_dim=3)
    cache._client = AsyncMock()
    cache._connected = True
    cache._semantic_ready = True

    assert await cache.get_cache("tenant", [0.1, 0.2]) is None
    assert await cache.set_cache("tenant", [0.1, 0.2], "answer") is False
    cache._client.execute_command.assert_not_awaited()
    cache._client.pipeline.assert_not_called()


@pytest.mark.asyncio
async def test_cache_closes_client_when_connect_ping_fails() -> None:
    cache = SemanticCacheManager()
    client = AsyncMock()
    client.ping.side_effect = RuntimeError("redis down")

    with patch("redis.asyncio.from_url", return_value=client):
        await cache.connect()

    client.aclose.assert_awaited_once()
    assert cache.connected is False


@pytest.mark.asyncio
async def test_router_response_cost_is_per_request_not_cumulative() -> None:
    backend = AsyncMock()
    backend.generate.return_value = {
        "content": "ok",
        "input_tokens": 1000,
        "output_tokens": 1000,
    }
    router = ModelRouter(backends={BASIC_MODEL: backend})

    first = await router.route(
        GatewayRequest(user_id="u", tenant_id="t", question="first")
    )
    second = await router.route(
        GatewayRequest(user_id="u", tenant_id="t", question="second")
    )

    assert second.estimated_cost_usd == first.estimated_cost_usd


@pytest.mark.asyncio
async def test_provider_factory_requires_close_before_reinitializing() -> None:
    config = SimpleNamespace(
        kagent_llm_provider="openai",
        provider_routing_strategy="priority",
        openai_api_key="key",
        deepseek_api_key="",
        gemini_api_key="",
        openai_model="model",
        openai_api_url="https://example.invalid",
    )
    factory = ProviderFactory()
    factory.init(config)
    factory.get_all_providers()

    with pytest.raises(RuntimeError, match="close"):
        factory.init(config)

    await factory.close()
    factory.init(config)


@pytest.mark.asyncio
async def test_mcp_tool_call_has_operation_timeout() -> None:
    async def never_finishes(*_: object, **__: object) -> object:
        await asyncio.sleep(1)
        return SimpleNamespace(content=[], structuredContent=None, isError=False)

    session = MagicMock()
    session.call_tool = never_finishes
    client = MCPClient("test", "unused", operation_timeout=0.01)
    client._session = session

    with pytest.raises(asyncio.TimeoutError):
        await client.call_tool("slow", {})


@pytest.mark.asyncio
async def test_mcp_concurrent_connect_starts_one_session(monkeypatch: pytest.MonkeyPatch) -> None:
    starts = 0

    class Context:
        def __init__(self, value: object) -> None:
            self.value = value

        async def __aenter__(self) -> object:
            return self.value

        async def __aexit__(self, *_: object) -> None:
            return None

    def fake_stdio_client(_: object) -> Context:
        nonlocal starts
        starts += 1
        return Context((object(), object()))

    class FakeSession:
        def __init__(self, *_: object) -> None:
            pass

        async def __aenter__(self) -> "FakeSession":
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def initialize(self) -> object:
            await asyncio.sleep(0)
            return SimpleNamespace(capabilities={})

    monkeypatch.setattr("src.core.mcp.client.stdio_client", fake_stdio_client)
    monkeypatch.setattr("src.core.mcp.client.ClientSession", FakeSession)
    client = MCPClient("test", "unused")

    await asyncio.gather(client.connect(), client.connect())

    assert starts == 1
    await client.close()


@pytest.mark.parametrize(("k", "top_k"), [(-1, 20), (60, 0)])
def test_rrf_rejects_invalid_parameters(k: int, top_k: int) -> None:
    with pytest.raises(ValueError):
        reciprocal_rank_fusion([], [], k=k, top_k=top_k)


def test_gateway_request_normalizes_identity_fields() -> None:
    request = GatewayRequest(
        user_id=" user ",
        tenant_id=" tenant ",
        session_id=" session ",
        question="hello",
    )

    assert request.user_id == "user"
    assert request.tenant_id == "tenant"
    assert request.session_id == "session"


def test_tool_schema_uses_annotations_and_hides_trusted_context() -> None:
    registry = get_registry()

    @tool(name="typed_review_tool")
    async def typed_review_tool(
        values: list[int],
        limit: int | None = None,
        tenant_id: str = "",
    ) -> str:
        return str((values, limit, tenant_id))

    try:
        registered = registry.get("typed_review_tool")
        assert registered is not None
        schema = registered.to_openai_tool()["function"]["parameters"]
        assert schema["properties"]["values"]["type"] == "array"
        assert "tenant_id" not in schema["properties"]

        validated = registered.validate_arguments({"values": [1], "limit": "2"})
        assert validated["limit"] == 2
    finally:
        registry.unregister("typed_review_tool")


def test_variadic_mcp_handler_keeps_keyword_arguments_flat() -> None:
    async def handler(**kwargs: object) -> str:
        return str(kwargs)

    registered = Tool(
        "mcp_test",
        "test",
        handler,
        ToolSpec("mcp_test", "test", {"type": "object", "properties": {}}),
    )

    assert registered.validate_arguments({"query": "hello"}) == {"query": "hello"}
