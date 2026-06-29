"""模型路由与 token 成本统计。

本模块负责维护模型后端、请求路由、token 计数和成本估算。它不负责具体
业务流程编排、SSE 输出或前端状态展示。
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Protocol, Any

from src.config import config, ModelPricing
from src.core.schemas import GatewayRequest, GatewayResponse

logger = logging.getLogger("kagent.router")


# ── 模型后端抽象 ────────────────────────────────────────────────

class LLMBackend(Protocol):
    """任何可调用的 LLM 后端都必须满足此协议。"""

    model_name: str

    async def generate(
        self,
        messages: list[Dict[str, str]],
        *,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> Dict[str, Any]:
        """返回 ``{"content": str, "input_tokens": int, "output_tokens": int}``"""
        ...  # pragma: no cover


# ── Token 成本估算器 ────────────────────────────────────────────

@dataclass
class TokenCounter:
    """按模型单价累计并预估请求财务成本。"""

    _totals: Dict[str, Dict[str, float]] = field(default_factory=dict, init=False)

    def record(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        if model not in self._totals:
            self._totals[model] = {"input": 0.0, "output": 0.0}
        self._totals[model]["input"] += input_tokens
        self._totals[model]["output"] += output_tokens

    def estimate_cost(self, model: str) -> float:
        """根据配置定价估算当前累计成本（USD）。"""
        if model not in self._totals:
            return 0.0
        pricing = config.pricing_for(model)
        t = self._totals[model]
        return (t["input"] / 1000) * pricing.input_price_per_1k + (t["output"] / 1000) * pricing.output_price_per_1k

    def total_cost(self) -> float:
        return sum(self.estimate_cost(m) for m in self._totals)

    def reset(self) -> None:
        self._totals.clear()


# ── 动态路由器 ──────────────────────────────────────────────────

# 路由阈值常量
ADVANCED_REASONING_MODEL: str = "deepseek-r1"
ADVANCED_REASONING_MODEL_FALLBACK: str = "claude-3.5-sonnet"
BASIC_MODEL: str = "qwen3-8b-instruct"


@dataclass
class ModelRouter:
    """根据请求特征动态选择模型后端。"""

    backends: Dict[str, LLMBackend] = field(default_factory=dict)
    token_counter: TokenCounter = field(default_factory=TokenCounter)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    # ── 路由决策 ────────────────────────────────────────────────

    def _select_model(self, request: GatewayRequest) -> str:
        """纯函数：决定使用哪个模型。"""
        # 条件 1：显式高级推理请求
        if request.advanced_reasoning:
            return self._pick_advanced()
        # 条件 2：问题字数超过阈值
        if len(request.question) > config.advanced_reasoning_threshold:
            return self._pick_advanced()
        return BASIC_MODEL

    def _pick_advanced(self) -> str:
        """优先 DeepSeek-R1，回退 Claude-3.5-Sonnet。"""
        if ADVANCED_REASONING_MODEL in self.backends:
            return ADVANCED_REASONING_MODEL
        if ADVANCED_REASONING_MODEL_FALLBACK in self.backends:
            logger.warning("DeepSeek-R1 不可用，回退到 Claude-3.5-Sonnet")
            return ADVANCED_REASONING_MODEL_FALLBACK
        # 两者均无则回退到基础模型（尽力而为）
        logger.error("高级推理后端均未注册，回退到基础模型")
        return BASIC_MODEL

    # ── 异步分发 ────────────────────────────────────────────────

    async def route(self, request: GatewayRequest) -> GatewayResponse:
        """核心路由方法：选择模型 → 调用 → 计费 → 返回。"""
        model = self._select_model(request)
        backend = self.backends.get(model)
        if backend is None:
            raise ModelNotAvailableError(f"模型 {model} 未注册到路由器")

        messages = [{"role": "user", "content": request.question}]
        t0 = time.perf_counter()

        try:
            result = await asyncio.wait_for(
                backend.generate(messages),
                timeout=120.0,
            )
        except asyncio.TimeoutError:
            raise ModelTimeoutError(f"模型 {model} 调用超时 (120s)")
        except Exception as exc:
            raise ModelInvocationError(f"模型 {model} 调用异常: {exc}") from exc

        latency_ms = (time.perf_counter() - t0) * 1000
        input_tokens = result.get("input_tokens", 0)
        output_tokens = result.get("output_tokens", 0)

        # 线程安全地累计 token
        async with self._lock:
            self.token_counter.record(model, input_tokens, output_tokens)

        cost = self.token_counter.estimate_cost(model)
        logger.info(
            "model=%s in_tok=%d out_tok=%d cost=$%.6f latency=%.1fms",
            model, input_tokens, output_tokens, cost, latency_ms,
        )

        return GatewayResponse(
            session_id=request.session_id,
            model_used=model,
            answer=result.get("content", ""),
            token_input=input_tokens,
            token_output=output_tokens,
            estimated_cost_usd=round(cost, 8),
            latency_ms=round(latency_ms, 2),
        )

    async def print_session_summary(self) -> None:
        """会话结束时打印本次路由的总成本。"""
        async with self._lock:
            total = self.token_counter.total_cost()
        logger.info("本次会话累计预估成本: $%.6f", total)


# ── 异常定义 ────────────────────────────────────────────────────

class ModelNotAvailableError(Exception):
    """请求的模型后端未注册。"""


class ModelTimeoutError(Exception):
    """模型调用超时。"""


class ModelInvocationError(Exception):
    """模型调用过程中发生未预期异常。"""
