"""网关观测与本地指标聚合。

本模块负责 trace/span 生命周期、本地 metrics 聚合和可选 LangFuse 上报。
它不负责业务路由、前端展示或具体模型调用。
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.core.langfuse_exporter import export_trace_to_langfuse, init_langfuse_client

logger = logging.getLogger("kagent.core.observability")


# ── 单次请求的链路跨度 ──────────────────────────────────────────

@dataclass
class Span:
    """单个链路跨度（Span）—— 对应全链路中的一个阶段。"""

    name: str
    start_ms: float = 0.0
    end_ms: float = 0.0
    duration_ms: float = 0.0
    status: str = "ok"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def finish(self, status: str = "ok", **metadata: Any) -> None:
        self.end_ms = time.perf_counter() * 1000
        self.duration_ms = self.end_ms - self.start_ms
        self.status = status
        self.metadata.update(metadata)


# ── 单次请求的完整追踪 ─────────────────────────────────────────

@dataclass
class TraceContext:
    """一次完整请求的追踪上下文。

    通过 trace_id 将前端请求、Qdrant 检索、BGE 精排、
    模型路由、Redis 写入这 5 个异步模块强行串联在同一根调用树上。
    """

    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = ""
    user_id: str = ""
    session_id: str = ""
    question: str = ""

    # 全链路时间戳
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    t_start: float = field(default_factory=time.perf_counter)

    # 各阶段跨度
    spans: Dict[str, Span] = field(default_factory=dict)

    # 聚合指标
    cache_hit: bool = False
    model_used: str = ""
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    ttft_ms: float = 0.0
    total_latency_ms: float = 0.0

    def start_span(self, name: str) -> Span:
        """开始一个新的链路跨度。"""
        span = Span(name=name, start_ms=time.perf_counter() * 1000)
        self.spans[name] = span
        return span

    def finish_span(self, name: str, status: str = "ok", **metadata: Any) -> None:
        """结束指定的链路跨度。"""
        if name in self.spans:
            self.spans[name].finish(status=status, **metadata)

    def finalize(self) -> None:
        """最终化追踪数据。"""
        self.total_latency_ms = (time.perf_counter() - self.t_start) * 1000

    def to_dict(self) -> Dict[str, Any]:
        """序列化为可导出的字典。"""
        return {
            "trace_id": self.trace_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "ttft_ms": round(self.ttft_ms, 2),
            "total_latency_ms": round(self.total_latency_ms, 2),
            "cache_hit": self.cache_hit,
            "model_used": self.model_used,
            "total_tokens": self.total_tokens,
            "estimated_cost_usd": round(self.estimated_cost_usd, 8),
            "spans": {
                name: {
                    "duration_ms": round(s.duration_ms, 2),
                    "status": s.status,
                    **s.metadata,
                }
                for name, s in self.spans.items()
            },
        }


# ── 全局度量聚合器 ──────────────────────────────────────────────

@dataclass
class MetricsAggregator:
    """全局度量聚合器 — 线程安全地累计所有请求指标。"""

    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    # 累计统计
    total_requests: int = 0
    total_cache_hits: int = 0
    total_cache_misses: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    total_latency_ms: float = 0.0

    # 延迟分布（简单分桶）
    latency_buckets: Dict[str, int] = field(default_factory=dict)

    # 最近 N 条 trace
    recent_traces: List[Dict[str, Any]] = field(default_factory=list)
    max_recent: int = 100

    async def record_trace(self, ctx: TraceContext) -> None:
        """记录一条完成的追踪数据。"""
        async with self._lock:
            self.total_requests += 1
            if ctx.cache_hit:
                self.total_cache_hits += 1
            else:
                self.total_cache_misses += 1
            self.total_tokens += ctx.total_tokens
            self.total_cost_usd += ctx.estimated_cost_usd
            self.total_latency_ms += ctx.total_latency_ms

            # 延迟分桶
            bucket = self._bucketize(ctx.total_latency_ms)
            self.latency_buckets[bucket] = self.latency_buckets.get(bucket, 0) + 1

            # 保留最近 N 条
            trace_dict = ctx.to_dict()
            self.recent_traces.append(trace_dict)
            if len(self.recent_traces) > self.max_recent:
                self.recent_traces = self.recent_traces[-self.max_recent:]

    @staticmethod
    def _bucketize(latency_ms: float) -> str:
        if latency_ms < 100:
            return "<100ms"
        elif latency_ms < 500:
            return "100-500ms"
        elif latency_ms < 1000:
            return "500ms-1s"
        elif latency_ms < 5000:
            return "1-5s"
        else:
            return ">5s"

    def snapshot(self) -> Dict[str, Any]:
        """返回当前度量快照。"""
        cache_total = self.total_cache_hits + self.total_cache_misses
        return {
            "total_requests": self.total_requests,
            "cache_hit_rate": round(self.total_cache_hits / max(cache_total, 1), 4),
            "cache_hits": self.total_cache_hits,
            "cache_misses": self.total_cache_misses,
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost_usd, 8),
            "avg_latency_ms": round(self.total_latency_ms / max(self.total_requests, 1), 2),
            "latency_distribution": self.latency_buckets.copy(),
        }


# ── Gateway Observer（核心）─────────────────────────────────────

@dataclass
class GatewayObserver:
    """全链路异步链路追踪观察者。

    在不阻塞 FastAPI 主流程的前提下，异步捕捉全链路每个阶段耗时。
    通过 trace_id 将 5 个异步并发模块强行串联在同一根调用树上。

    使用方式：
        ctx = observer.start_trace(request)
        # ... 各阶段调用 observer.span(ctx, "phase_name") ...
        observer.end_trace(ctx)
    """

    _langfuse_client: Any = field(default=None, init=False, repr=False)
    _metrics: MetricsAggregator = field(default_factory=MetricsAggregator, init=False)

    async def init_langfuse(self) -> None:
        """初始化 LangFuse 客户端（可选，失败时降级为本地追踪）。"""
        self._langfuse_client = init_langfuse_client()

    def start_trace(
        self,
        *,
        tenant_id: str,
        user_id: str,
        session_id: str,
        question: str,
    ) -> TraceContext:
        """开始一次新的链路追踪。"""
        ctx = TraceContext(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            question=question[:200],
        )
        logger.info("Trace 开始: trace_id=%s tenant=%s", ctx.trace_id[:8], tenant_id)
        return ctx

    def start_span(self, ctx: TraceContext, name: str) -> Span:
        """开始一个链路跨度。"""
        return ctx.start_span(name)

    def finish_span(
        self,
        ctx: TraceContext,
        name: str,
        *,
        status: str = "ok",
        **metadata: Any,
    ) -> None:
        """结束一个链路跨度。"""
        ctx.finish_span(name, status=status, **metadata)

    async def end_trace(self, ctx: TraceContext) -> Dict[str, Any]:
        """结束链路追踪并导出数据。"""
        ctx.finalize()

        # 异步推送到 LangFuse（不阻塞）
        if self._langfuse_client is not None:
            try:
                await asyncio.to_thread(export_trace_to_langfuse, self._langfuse_client, ctx)
            except Exception as exc:
                logger.warning("LangFuse 导出失败: %s", exc)

        # 记录到本地度量
        await self._metrics.record_trace(ctx)

        logger.info(
            "Trace 完成: trace_id=%s latency=%.1fms tokens=%d cost=$%.6f cache_hit=%s",
            ctx.trace_id[:8], ctx.total_latency_ms, ctx.total_tokens,
            ctx.estimated_cost_usd, ctx.cache_hit,
        )

        return ctx.to_dict()

    @property
    def metrics(self) -> MetricsAggregator:
        return self._metrics


# ── 全局单例 ────────────────────────────────────────────────────
observer = GatewayObserver()
