"""SSE 协议底层契约测试。"""

from __future__ import annotations

import json
import asyncio
from types import SimpleNamespace

from src.application.stream_contract import (
    PROTOCOL_VERSION,
    contract_payload,
    error_frame,
    metadata_frame,
    sse_done,
    text_frame,
)


def decode_frame(frame: str) -> dict:
    assert frame.startswith("data: ")
    assert frame.endswith("\n\n")
    return json.loads(frame.removeprefix("data: ").strip())


def test_text_frame_contract() -> None:
    payload = decode_frame(text_frame("hello"))

    assert payload == {
        "protocol_version": PROTOCOL_VERSION,
        "status": "text",
        "event": "text",
        "text": "hello",
    }


def test_metadata_frame_contract() -> None:
    payload = decode_frame(metadata_frame(trace_id="trace-1", total_tokens=100))

    assert payload["protocol_version"] == PROTOCOL_VERSION
    assert payload["status"] == "metadata"
    assert payload["event"] == "metadata"
    assert payload["text"] == ""
    assert payload["trace_id"] == "trace-1"
    assert payload["total_tokens"] == 100


def test_error_frame_contract() -> None:
    payload = decode_frame(error_frame("error msg"))

    assert payload["protocol_version"] == PROTOCOL_VERSION
    assert payload["status"] == "error"
    assert payload["event"] == "error"
    assert payload["text"] == ""
    assert payload["error"] == "error msg"


def test_sse_done_contract() -> None:
    assert sse_done() == "data: [DONE]\n\n"


def test_contract_payload_lists_supported_statuses() -> None:
    payload = contract_payload()

    assert payload["protocol_version"] == PROTOCOL_VERSION
    assert payload["stream"]["done_sentinel"] == "[DONE]"
    assert payload["stream"]["statuses"] == ["text", "info", "metadata", "error"]
    assert payload["stream"]["phases"] == [
        "checking_cache",
        "cache_hit",
        "running_fast_lane",
        "retrieving_knowledge",
        "waiting_provider",
        "running_agent",
    ]


def test_metrics_expose_cache_readiness(monkeypatch) -> None:
    from src.api import routes

    cache = SimpleNamespace(connected=True, semantic_ready=False, namespace_version="v2")
    payload = routes.build_metrics_payload(cache)

    assert payload["cache"] == {
        "connected": True,
        "semantic_ready": False,
        "namespace_version": "v2",
    }


def test_metrics_classify_cache_and_fast_lane_sources() -> None:
    from src.core.observability import MetricsAggregator, TraceContext

    metrics = MetricsAggregator()
    exact = TraceContext(cache_hit=True, cache_hit_type="exact", response_source="cache")
    semantic = TraceContext(cache_hit=True, cache_hit_type="semantic", response_source="cache")
    calculator = TraceContext(response_source="calculator")

    asyncio.run(metrics.record_trace(exact))
    asyncio.run(metrics.record_trace(semantic))
    asyncio.run(metrics.record_trace(calculator))

    snapshot = metrics.snapshot()
    assert snapshot["exact_cache_hits"] == 1
    assert snapshot["semantic_cache_hits"] == 1
    assert snapshot["fast_lane_hits"] == 1
