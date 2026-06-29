"""
KAgent 真实指标测试脚本
==============================

用途：
  1. 测试 DeepSeek API 真实 TTFT / 总延迟
  2. 测试语义缓存命中效果（命中后延迟应该 <5ms）
  3. 测试 200 并发 SSE 长连接（需要 Locust，见下方）
  4. 输出可直接写进简历的指标报告

前置条件：
  - KAgent 已启动（python -m uvicorn src.main:app --host 0.0.0.0 --port 8000）
  - .env 中已配置 LLM_API_KEY

运行方式：
  cd "D:/claude code"
  python tests/benchmark_metrics.py
"""

from __future__ import annotations

import asyncio
import json
import time
import statistics
from dataclasses import dataclass, field
from typing import List, Optional

import httpx


# ── 配置 ────────────────────────────────────────────────────────
GATEWAY_URL = "http://localhost:8000"
API_V1 = f"{GATEWAY_URL}/api/v1/gateway"

# 测试用请求（模拟真实用户问题）
TEST_QUESTIONS = [
    {"question": "什么是 Kubernetes？", "tenant_id": "tenant_test", "user_id": "user_001"},
    {"question": "请解释一下 Docker 容器和虚拟机的区别", "tenant_id": "tenant_test", "user_id": "user_001"},
    {"question": "如何设计一个高可用的微服务架构？", "tenant_id": "tenant_test", "user_id": "user_002"},
    {"question": "Python asyncio 的 event loop 是怎么工作的？", "tenant_id": "tenant_test", "user_id": "user_001"},
    {"question": "什么是 RAG？它和 Fine-tuning 有什么区别？", "tenant_id": "tenant_test", "user_id": "user_003"},
]

SHORT_QUESTIONS = [
    {"question": "什么是 API？", "tenant_id": "tenant_test", "user_id": "user_001"},
    {"question": "HTTP 和 HTTPS 的区别", "tenant_id": "tenant_test", "user_id": "user_001"},
]


# ── 数据结构 ────────────────────────────────────────────────────
@dataclass
class RequestMetrics:
    question: str
    ttft_ms: float            # Time To First Token（第一个 text chunk 到达的时间）
    total_latency_ms: float   # 总延迟（从发送请求到收到 [DONE] 信号）
    token_count: int          # 收到的 text chunk 数
    cache_hit: bool = False
    error: Optional[str] = None


@dataclass
class BenchmarkReport:
    total_requests: int = 0
    success: int = 0
    failures: int = 0
    ttft_list: List[float] = field(default_factory=list)
    latency_list: List[float] = field(default_factory=list)
    token_count_list: List[int] = field(default_factory=list)
    cache_hits: int = 0
    cache_misses: int = 0

    def print_report(self) -> None:
        print("\n" + "=" * 60)
        print("  KAGENT 性能测试报告")
        print("=" * 60)
        print(f"  总请求数:  {self.total_requests}")
        print(f"  成功:      {self.success}")
        print(f"  失败:      {self.failures}")
        if self.cache_hits + self.cache_misses > 0:
            hit_rate = self.cache_hits / (self.cache_hits + self.cache_misses) * 100
            print(f"  缓存命中:  {hit_rate:.1f}%  ({self.cache_hits}/{self.cache_hits + self.cache_misses})")
        print()
        if self.ttft_list:
            print("  -- TTFT (首 Token 延迟) -------------------------")
            s = sorted(self.ttft_list)
            print(f"    P50 (中位数): {statistics.median(self.ttft_list):.1f} ms")
            if len(s) >= 10:
                print(f"    P90:           {s[int(len(s)*0.9)]:.1f} ms")
            else:
                print(f"    P90:           N/A (需 >=10 samples)")
            print(f"    Min:           {min(s):.1f} ms")
            print(f"    Max:           {max(s):.1f} ms")
            print(f"    Mean:          {statistics.mean(self.ttft_list):.1f} ms")
        print()
        if self.latency_list:
            s = sorted(self.latency_list)
            print("  -- Total Latency (总延迟) -----------------------")
            print(f"    P50:           {statistics.median(self.latency_list):.1f} ms")
            print(f"    Mean:          {statistics.mean(self.latency_list):.1f} ms")
            print(f"    Min:           {min(s):.1f} ms")
            print(f"    Max:           {max(s):.1f} ms")
        print()
        if self.token_count_list:
            avg_tokens = statistics.mean(self.token_count_list)
            print("  -- Token Output ---------------------------------")
            print(f"    Avg chunks:    {avg_tokens:.0f}")
            # DeepSeek-chat 定价: input $0.14/M, output $0.28/M
            est_cost = (200 * 0.14 + avg_tokens * 0.28) / 1_000_000
            print(f"    Est cost/req:  ~${est_cost:.6f} (~{est_cost*7.2:.4f} CNY)")
        print()
        print("  -- Resume-Ready Data ------------------------------")
        if self.ttft_list:
            p50 = statistics.median(self.ttft_list)
            s = sorted(self.ttft_list)
            if len(s) >= 10:
                p90 = s[int(len(s)*0.9)]
                print(f"    TTFT P50: {p50:.0f}ms, P90: {p90:.0f}ms")
            else:
                print(f"    TTFT P50: {p50:.0f}ms")
        if self.cache_hits + self.cache_misses > 0:
            hit_rate = self.cache_hits / (self.cache_hits + self.cache_misses) * 100
            print(f"    Cache hit rate: {hit_rate:.1f}%")
        if self.token_count_list:
            avg = statistics.mean(self.token_count_list)
            print(f"    Avg output chunks: ~{avg:.0f}")
        print("=" * 60)

    def to_markdown(self) -> str:
        lines = ["## KAgent Performance Metrics (Real LLM API)\n"]
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        if self.ttft_list:
            lines.append(f"| TTFT P50 | {statistics.median(self.ttft_list):.0f} ms |")
            s = sorted(self.ttft_list)
            if len(s) >= 10:
                lines.append(f"| TTFT P90 | {s[int(len(s)*0.9)]:.0f} ms |")
        if self.cache_hits + self.cache_misses > 0:
            hit_rate = self.cache_hits / (self.cache_hits + self.cache_misses) * 100
            lines.append(f"| Semantic cache hit rate | {hit_rate:.1f}% |")
        if self.token_count_list:
            lines.append(f"| Avg output chunks | {statistics.mean(self.token_count_list):.0f} |")
        return "\n".join(lines)


# ── 核心测试函数 ────────────────────────────────────────────────

async def measure_single_request(
    client: httpx.AsyncClient,
    question_data: dict,
    request_id: int,
) -> RequestMetrics:
    """发送单个 SSE 请求，测量 TTFT 和总延迟。

    SSE 协议：
      - 每个数据行格式为 "data: {json}\\n"
      - 事件之间用空行分隔
      - 流以 "data: [DONE]\\n" 结束
    """
    payload = {
        "user_id": question_data["user_id"],
        "tenant_id": question_data["tenant_id"],
        "question": question_data["question"],
        "department": "general",
    }

    t_start = time.perf_counter()
    ttft_ms = -1
    total_latency_ms = -1
    token_count = 0
    cache_hit = False
    error = None

    try:
        async with client.stream("POST", f"{API_V1}/stream", json=payload) as resp:
            if resp.status_code != 200:
                error = f"HTTP {resp.status_code}"
                total_latency_ms = (time.perf_counter() - t_start) * 1000
                return RequestMetrics(
                    question=question_data["question"][:50],
                    ttft_ms=0, total_latency_ms=total_latency_ms,
                    token_count=0, error=error,
                )

            async for raw_line in resp.aiter_lines():
                line = raw_line.strip()

                # SSE 结束标志
                if line == "data: [DONE]":
                    total_latency_ms = (time.perf_counter() - t_start) * 1000
                    break

                # 解析数据行
                if not line.startswith("data: "):
                    continue

                data_str = line[6:]
                if not data_str:
                    continue

                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                # 检测缓存命中（第一条 status 消息里带 cache_hit 字段）
                if "cache_hit" in data and data["cache_hit"] is True:
                    cache_hit = True

                # TTFT: 第一个包含 "text" 字段的 chunk 到达时间
                if "text" in data and data["text"] and ttft_ms < 0:
                    ttft_ms = (time.perf_counter() - t_start) * 1000

                # 统计 text chunk 数量
                if "text" in data and data["text"]:
                    token_count += 1

    except httpx.RemoteProtocolError:
        # httpx 在 chunked stream 关闭时会报这个错
        # 这是正常的——服务端发完 [DONE] 后关闭连接，httpx 认为不完整
        # 只要我们已经记录了数据就忽略
        if total_latency_ms < 0:
            total_latency_ms = (time.perf_counter() - t_start) * 1000
        if ttft_ms < 0 and token_count == 0:
            error = "RemoteProtocolError: connection closed before any token received"
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        total_latency_ms = (time.perf_counter() - t_start) * 1000

    # 兜底：如果 [DONE] 没被检测到，用最后的记录时间
    if total_latency_ms < 0:
        total_latency_ms = (time.perf_counter() - t_start) * 1000

    return RequestMetrics(
        question=question_data["question"][:50],
        ttft_ms=max(ttft_ms, 0),
        total_latency_ms=max(total_latency_ms, 0),
        token_count=token_count,
        cache_hit=cache_hit,
        error=error,
    )


async def test_health() -> bool:
    try:
        async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
            resp = await client.get(f"{GATEWAY_URL}/health")
            return resp.status_code == 200
    except Exception:
        return False


async def run_benchmark(
    questions: List[dict],
    concurrency: int = 1,
    label: str = "test",
) -> BenchmarkReport:
    report = BenchmarkReport()
    report.total_requests = len(questions)

    print(f"\n>> {label} ({len(questions)} requests, concurrency={concurrency})")

    async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=15), trust_env=False) as client:
        semaphore = asyncio.Semaphore(concurrency)

        async def _run_one(q, idx):
            async with semaphore:
                print(f"  [{idx+1}/{len(questions)}] {q['question'][:40]}...")
                m = await measure_single_request(client, q, idx)
                return m

        tasks = [_run_one(q, i) for i, q in enumerate(questions)]
        results = await asyncio.gather(*tasks)

    for m in results:
        if m.error:
            report.failures += 1
            print(f"    X {m.error[:80]}")
        else:
            report.success += 1
            report.ttft_list.append(m.ttft_ms)
            report.latency_list.append(m.total_latency_ms)
            report.token_count_list.append(m.token_count)
            if m.cache_hit:
                report.cache_hits += 1
            else:
                report.cache_misses += 1
            print(f"    OK TTFT={m.ttft_ms:.0f}ms total={m.total_latency_ms:.0f}ms chunks={m.token_count} cache={m.cache_hit}")

    report.print_report()
    return report


async def test_cache_effect() -> None:
    print("\n>> Cache effect test (same question x3)")
    question = TEST_QUESTIONS[0]
    results = []

    async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=15), trust_env=False) as client:
        for i in range(3):
            print(f"  Round {i+1}/3...")
            m = await measure_single_request(client, question, 0)
            results.append(m)
            if m.error:
                print(f"    X {m.error[:80]}")
            else:
                print(f"    TTFT={m.ttft_ms:.0f}ms total={m.total_latency_ms:.0f}ms cache_hit={m.cache_hit}")

    # 分析
    if len(results) >= 2 and all(not r.error for r in results):
        if results[0].ttft_ms > 0 and results[1].ttft_ms > 0:
            speedup = results[0].ttft_ms / results[1].ttft_ms if results[1].ttft_ms > 0 else 0
            print(f"\n  Summary:")
            print(f"    1st TTFT: {results[0].ttft_ms:.0f}ms")
            print(f"    2nd TTFT: {results[1].ttft_ms:.0f}ms")
            if results[1].cache_hit:
                print(f"    Cache hit! Speedup: {speedup:.1f}x")
            elif results[2].cache_hit:
                print(f"    3rd hit cache. Speedup: {results[0].ttft_ms / results[2].ttft_ms:.1f}x")
            else:
                print(f"    No cache hit detected (may need same embedding)")


async def check_metrics_endpoint() -> None:
    print("\n>> Gateway metrics endpoint...")
    try:
        async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
            resp = await client.get(f"{API_V1}/metrics")
            if resp.status_code == 200:
                data = resp.json()
                print(f"  {json.dumps(data, indent=2, ensure_ascii=False)}")
            else:
                print(f"  /metrics returned {resp.status_code}")
    except Exception as exc:
        print(f"  Failed: {exc}")


# ── 主入口 ──────────────────────────────────────────────────────

async def main() -> None:
    print("KAgent Real Metrics Benchmark")
    print("=" * 60)

    # 1. 健康检查
    print("\n[1/4] Health check...")
    if not await test_health():
        print("  X Gateway not running!")
        print("  Start it first: cd D:/claude code && python -m uvicorn src.main:app --port 8000")
        return
    print("  OK Gateway is running")

    # 2. 预热（首次请求可能慢，不计入统计）
    print("\n[2/4] Warmup request (first call initializes BM25, connections)...")
    async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=15), trust_env=False) as client:
        m = await measure_single_request(client, TEST_QUESTIONS[0], 0)
        if m.error:
            print(f"  X Warmup failed: {m.error}")
            print("  Check: LLM_API_KEY in .env, Redis/Qdrant running if needed")
            return
        print(f"  OK Warmup TTFT: {m.ttft_ms:.0f}ms")

    # 3. 正式基准测试（5 个不同问题，顺序执行）
    print("\n[3/4] Benchmark (5 sequential requests)...")
    report = await run_benchmark(TEST_QUESTIONS[:5], concurrency=1, label="Benchmark")

    # 4. 缓存效果测试
    print("\n[4/4] Cache effect test...")
    await test_cache_effect()

    # 5. 读取网关内置指标
    await check_metrics_endpoint()

    # 最终 Markdown 输出
    print("\n" + "=" * 60)
    print("  FINAL REPORT (copy to resume)")
    print("=" * 60)
    print(report.to_markdown())
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
