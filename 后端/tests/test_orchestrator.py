"""ChatOrchestrator 核心编排链路测试。"""

from __future__ import annotations

import json
import asyncio
from types import SimpleNamespace
from typing import AsyncGenerator
from unittest.mock import AsyncMock, Mock

import pytest

from src.application import chat_flows, orchestrator as orchestrator_module
from src.application.orchestrator import ChatOrchestrator
from src.core.observability import GatewayObserver
from src.core.protection import CircuitBreaker
from src.core.router import ModelRouter
from src.core.schemas import GatewayRequest


class ConnectedRequest:
    async def is_disconnected(self) -> bool:
        return False


async def immediate_tokens(text: str, **_: object) -> AsyncGenerator[str, None]:
    yield text


async def collect_frames(orchestrator: ChatOrchestrator, request: GatewayRequest) -> list[str]:
    return [frame async for frame in orchestrator.stream(request, ConnectedRequest())]


def decode_frame(frame: str) -> dict:
    return json.loads(frame.removeprefix("data: ").strip())


def make_request() -> GatewayRequest:
    return GatewayRequest(
        user_id="user-1",
        tenant_id="tenant-1",
        question="test question",
        session_id="session-1",
    )


def make_orchestrator(
    *,
    agent_runtime: object,
    semantic_cache: object | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    provider_factory: object | None = None,
    rag_service: object | None = None,
    fast_lane: object | None = None,
) -> ChatOrchestrator:
    return ChatOrchestrator(
        model_router=ModelRouter(),
        agent_runtime=agent_runtime,
        semantic_cache=semantic_cache,
        circuit_breaker=circuit_breaker,
        observer=GatewayObserver(),
        provider_factory=provider_factory,
        rag_service=rag_service,
        fast_lane=fast_lane,
    )


class StubProviderFactory:
    def __init__(self, chunks: list[str]) -> None:
        self.chunks = chunks
        self.stream_calls = 0
        self.messages: list[dict] = []

    async def chat_stream_with_fallback(self, messages, *, on_provider_selected, **_):
        self.stream_calls += 1
        self.messages = messages
        on_provider_selected("deepseek", "deepseek-chat")
        for chunk in self.chunks:
            yield chunk


@pytest.mark.asyncio
async def test_open_circuit_breaker_returns_degraded_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orchestrator_module, "simulate_llm_tokens", immediate_tokens)
    agent_runtime = AsyncMock()
    breaker = CircuitBreaker(recovery_timeout=60)
    breaker.force_open()
    orchestrator = make_orchestrator(agent_runtime=agent_runtime, circuit_breaker=breaker)

    frames = await collect_frames(orchestrator, make_request())
    payloads = [decode_frame(frame) for frame in frames[:-1]]

    assert frames[-1] == "data: [DONE]\n\n"
    degraded = [payload for payload in payloads if payload["status"] == "text"]
    assert degraded
    assert degraded[-1]["circuit_breaker"] is True
    assert payloads[-1]["status"] == "metadata"
    assert payloads[-1]["circuit_breaker"] is True
    agent_runtime.execute_graph.assert_not_awaited()


@pytest.mark.asyncio
async def test_cache_hit_skips_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orchestrator_module, "embed", lambda _: [0.1, 0.2])
    monkeypatch.setattr(chat_flows, "simulate_llm_tokens", immediate_tokens)
    cache = AsyncMock()
    cache.get_exact_cache.return_value = None
    cache.get_cache.return_value = "cached answer"
    agent_runtime = AsyncMock()
    orchestrator = make_orchestrator(agent_runtime=agent_runtime, semantic_cache=cache)

    frames = await collect_frames(orchestrator, make_request())
    payloads = [decode_frame(frame) for frame in frames[:-1]]

    cache.get_cache.assert_awaited_once_with(
        tenant_id="tenant-1",
        question_vector=[0.1, 0.2],
        department="general",
    )
    agent_runtime.execute_graph.assert_not_awaited()
    assert any(payload.get("cache_hit") is True for payload in payloads)
    assert any(payload.get("text") == "cached answer" for payload in payloads)
    metadata = [payload for payload in payloads if payload["status"] == "metadata"][-1]
    assert metadata["ttft_ms"] >= 0
    assert metadata["total_latency_ms"] >= metadata["ttft_ms"]
    assert metadata["cache_hit_type"] == "semantic"
    assert metadata["response_source"] == "cache"
    assert frames[-1] == "data: [DONE]\n\n"


@pytest.mark.asyncio
async def test_cache_miss_runs_agent_and_emits_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orchestrator_module, "embed", lambda _: [0.1, 0.2])
    monkeypatch.setattr(chat_flows, "embed", lambda _: [0.1, 0.2])
    cache = AsyncMock()
    cache.get_exact_cache.return_value = None
    cache.get_cache.return_value = None
    schedule_cache_write = Mock()
    monkeypatch.setattr(chat_flows, "_schedule_cache_write", schedule_cache_write)

    async def execute_graph(state):
        state.final_answer = "generated answer"
        state.provider_used = "deepseek"
        state.model_used = "deepseek-chat"
        state.iteration = 1
        state.steps = [{"action": "answer"}]
        return state

    agent_runtime = AsyncMock()
    agent_runtime.execute_graph.side_effect = execute_graph
    orchestrator = make_orchestrator(agent_runtime=agent_runtime, semantic_cache=cache)

    frames = await collect_frames(orchestrator, make_request())
    payloads = [decode_frame(frame) for frame in frames[:-1]]

    agent_runtime.execute_graph.assert_awaited_once()
    schedule_cache_write.assert_not_called()
    text = "".join(payload["text"] for payload in payloads if payload["status"] == "text")
    metadata = [payload for payload in payloads if payload["status"] == "metadata"]
    assert text == "generated answer"
    assert metadata[-1]["cache_hit"] is False
    assert metadata[-1]["agent_iterations"] == 1
    assert metadata[-1]["agent_steps"] == 1
    assert metadata[-1]["provider"] == "deepseek"
    assert metadata[-1]["model"] == "deepseek-chat"
    assert metadata[-1]["response_source"] == "agent"
    assert metadata[-1]["routing_decision"] == "qwen3-8b-instruct"
    assert frames[-1] == "data: [DONE]\n\n"


@pytest.mark.asyncio
async def test_open_circuit_still_serves_exact_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chat_flows, "simulate_llm_tokens", immediate_tokens)
    cache = AsyncMock()
    cache.connected = True
    cache.get_exact_cache.return_value = "cached while provider is down"
    breaker = CircuitBreaker(recovery_timeout=60)
    breaker.force_open()
    agent_runtime = AsyncMock()
    orchestrator = make_orchestrator(
        agent_runtime=agent_runtime,
        semantic_cache=cache,
        circuit_breaker=breaker,
    )

    frames = await collect_frames(orchestrator, make_request())
    payloads = [decode_frame(frame) for frame in frames[:-1]]

    assert any(payload.get("text") == "cached while provider is down" for payload in payloads)
    assert payloads[-1]["response_source"] == "cache"
    agent_runtime.execute_graph.assert_not_awaited()


@pytest.mark.asyncio
async def test_agent_request_enters_circuit_breaker_once() -> None:
    breaker = CircuitBreaker()

    async def execute_graph(state):
        state.final_answer = "agent answer"
        return state

    agent_runtime = AsyncMock()
    agent_runtime.execute_graph.side_effect = execute_graph
    orchestrator = make_orchestrator(
        agent_runtime=agent_runtime,
        circuit_breaker=breaker,
    )
    request = make_request().model_copy(update={"advanced_reasoning": True})

    await collect_frames(orchestrator, request)

    assert breaker.stats()["total_requests"] == 1


@pytest.mark.asyncio
async def test_direct_stream_reports_per_request_cost(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orchestrator_module.config, "fast_path_enabled", True)
    provider_factory = StubProviderFactory(["answer"])
    orchestrator = make_orchestrator(
        agent_runtime=AsyncMock(),
        provider_factory=provider_factory,
    )

    first_frames = await collect_frames(orchestrator, make_request())
    second_frames = await collect_frames(orchestrator, make_request())
    first = [decode_frame(frame) for frame in first_frames[:-1] if decode_frame(frame)["status"] == "metadata"][-1]
    second = [decode_frame(frame) for frame in second_frames[:-1] if decode_frame(frame)["status"] == "metadata"][-1]

    assert second["estimated_cost_usd"] == first["estimated_cost_usd"]


@pytest.mark.asyncio
async def test_direct_fast_path_streams_one_provider_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orchestrator_module.config, "fast_path_enabled", True)
    provider_factory = StubProviderFactory(["direct ", "answer"])
    agent_runtime = AsyncMock()
    orchestrator = make_orchestrator(
        agent_runtime=agent_runtime,
        provider_factory=provider_factory,
    )

    frames = await collect_frames(orchestrator, make_request())
    payloads = [decode_frame(frame) for frame in frames[:-1]]

    assert provider_factory.stream_calls == 1
    agent_runtime.execute_graph.assert_not_awaited()
    assert "".join(payload["text"] for payload in payloads if payload["status"] == "text") == "direct answer"
    assert payloads[-1]["provider"] == "deepseek"
    assert payloads[-1]["model"] == "deepseek-chat"
    assert payloads[-1]["response_source"] == "provider"


@pytest.mark.asyncio
async def test_knowledge_fast_path_retrieves_once_then_streams_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orchestrator_module.config, "fast_path_enabled", True)
    monkeypatch.setattr(orchestrator_module, "embed", lambda _: [0.3, 0.4])
    provider_factory = StubProviderFactory(["knowledge answer"])
    rag_service = AsyncMock()
    rag_service.retrieve.return_value = (
        [SimpleNamespace(text="travel policy evidence")],
        {"dense_hits": 1},
    )
    agent_runtime = AsyncMock()
    orchestrator = make_orchestrator(
        agent_runtime=agent_runtime,
        provider_factory=provider_factory,
        rag_service=rag_service,
    )
    request = make_request().model_copy(update={"question": "请查找内部报销政策"})

    await collect_frames(orchestrator, request)

    rag_service.retrieve.assert_awaited_once_with(
        query="请查找内部报销政策",
        tenant_id="tenant-1",
        department="general",
        top_k=3,
        query_vector=[0.3, 0.4],
    )
    assert provider_factory.stream_calls == 1
    assert "travel policy evidence" in provider_factory.messages[-1]["content"]
    agent_runtime.execute_graph.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "gateway_request",
    [
        make_request().model_copy(update={"advanced_reasoning": True}),
        make_request().model_copy(update={"question": "请调用工具计算一下"}),
    ],
)
async def test_advanced_and_tool_requests_keep_agent_path(
    monkeypatch: pytest.MonkeyPatch,
    gateway_request: GatewayRequest,
) -> None:
    monkeypatch.setattr(orchestrator_module.config, "fast_path_enabled", True)
    provider_factory = StubProviderFactory(["must not be used"])

    async def execute_graph(state):
        state.final_answer = "agent answer"
        state.iteration = 1
        return state

    agent_runtime = AsyncMock()
    agent_runtime.execute_graph.side_effect = execute_graph
    orchestrator = make_orchestrator(
        agent_runtime=agent_runtime,
        provider_factory=provider_factory,
    )

    await collect_frames(orchestrator, gateway_request)

    agent_runtime.execute_graph.assert_awaited_once()
    assert provider_factory.stream_calls == 0


@pytest.mark.asyncio
async def test_advanced_request_bypasses_all_cache_lookups(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orchestrator_module.config, "fast_path_enabled", True)
    cache = AsyncMock()
    cache.connected = True

    async def execute_graph(state):
        state.final_answer = "agent answer"
        return state

    agent_runtime = AsyncMock()
    agent_runtime.execute_graph.side_effect = execute_graph
    orchestrator = make_orchestrator(agent_runtime=agent_runtime, semantic_cache=cache)
    request = make_request().model_copy(update={"advanced_reasoning": True})

    await collect_frames(orchestrator, request)

    cache.get_exact_cache.assert_not_awaited()
    cache.get_cache.assert_not_awaited()


@pytest.mark.asyncio
async def test_fast_lane_skips_provider_and_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orchestrator_module.config, "fast_path_enabled", True)
    fast_lane = AsyncMock()
    fast_lane.try_answer.return_value = SimpleNamespace(answer="计算结果: 14", source="calculator")
    provider_factory = StubProviderFactory(["must not run"])
    agent_runtime = AsyncMock()
    orchestrator = make_orchestrator(
        agent_runtime=agent_runtime,
        provider_factory=provider_factory,
        fast_lane=fast_lane,
    )
    request = make_request().model_copy(update={"question": "请计算 2 * (3 + 4)"})

    frames = await collect_frames(orchestrator, request)
    payloads = [decode_frame(frame) for frame in frames[:-1]]

    assert "".join(payload["text"] for payload in payloads if payload["status"] == "text") == "计算结果: 14"
    assert payloads[-1]["response_source"] == "calculator"
    assert provider_factory.stream_calls == 0
    agent_runtime.execute_graph.assert_not_awaited()


@pytest.mark.asyncio
async def test_realtime_request_bypasses_cache_read_and_write(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orchestrator_module.config, "fast_path_enabled", True)
    cache = AsyncMock()
    cache.connected = True
    schedule_cache_write = Mock()
    monkeypatch.setattr(chat_flows, "_schedule_cache_write", schedule_cache_write)
    provider_factory = StubProviderFactory(["realtime answer"])
    orchestrator = make_orchestrator(
        agent_runtime=AsyncMock(),
        semantic_cache=cache,
        provider_factory=provider_factory,
    )
    request = make_request().model_copy(update={"question": "现在人民币汇率是多少？"})

    await collect_frames(orchestrator, request)

    cache.get_exact_cache.assert_not_awaited()
    cache.get_cache.assert_not_awaited()
    schedule_cache_write.assert_not_called()


@pytest.mark.asyncio
async def test_knowledge_fast_path_without_evidence_does_not_call_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(orchestrator_module.config, "fast_path_enabled", True)
    monkeypatch.setattr(orchestrator_module, "embed", lambda _: [0.3, 0.4])
    rag_service = AsyncMock()
    rag_service.retrieve.return_value = ([], {})
    provider_factory = StubProviderFactory(["hallucinated answer"])
    orchestrator = make_orchestrator(
        agent_runtime=AsyncMock(),
        provider_factory=provider_factory,
        rag_service=rag_service,
    )
    request = make_request().model_copy(update={"question": "请查找内部报销政策"})

    frames = await collect_frames(orchestrator, request)
    payloads = [decode_frame(frame) for frame in frames[:-1]]

    assert provider_factory.stream_calls == 0
    assert payloads[-1]["response_source"] == "knowledge_unavailable"


@pytest.mark.asyncio
async def test_direct_provider_is_cancelled_when_client_disconnects_before_first_chunk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(orchestrator_module.config, "fast_path_enabled", True)

    class DisconnectedRequest:
        async def is_disconnected(self) -> bool:
            return True

    class SlowProviderFactory:
        cancelled = False

        async def chat_stream_with_fallback(self, *_: object, **__: object):
            try:
                await asyncio.Event().wait()
                yield "never"
            finally:
                self.cancelled = True

    provider = SlowProviderFactory()
    orchestrator = make_orchestrator(
        agent_runtime=AsyncMock(),
        provider_factory=provider,
    )

    async def consume() -> list[str]:
        return [
            frame
            async for frame in orchestrator.stream(make_request(), DisconnectedRequest())
        ]

    await asyncio.wait_for(consume(), timeout=1)

    assert provider.cancelled is True


@pytest.mark.asyncio
async def test_provider_error_frame_does_not_expose_internal_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(orchestrator_module.config, "fast_path_enabled", True)

    class FailingProviderFactory:
        async def chat_stream_with_fallback(self, *_: object, **__: object):
            if False:
                yield ""
            raise RuntimeError("secret-internal-detail")

    orchestrator = make_orchestrator(
        agent_runtime=AsyncMock(),
        provider_factory=FailingProviderFactory(),
    )

    frames = await collect_frames(orchestrator, make_request())

    assert all("secret-internal-detail" not in frame for frame in frames)


@pytest.mark.asyncio
async def test_provider_wait_emits_sse_keepalive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orchestrator_module.config, "fast_path_enabled", True)
    monkeypatch.setattr(chat_flows, "SSE_KEEPALIVE_INTERVAL_S", 0.01, raising=False)

    class SlowProviderFactory:
        async def chat_stream_with_fallback(self, *_: object, **__: object):
            await asyncio.sleep(0.03)
            yield "answer"

    orchestrator = make_orchestrator(
        agent_runtime=AsyncMock(),
        provider_factory=SlowProviderFactory(),
    )

    frames = await collect_frames(orchestrator, make_request())

    assert ": ping\n\n" in frames
