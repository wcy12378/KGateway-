"""请求保护与熔断能力。

本模块负责熔断器状态机、失败统计和强制开关控制。它不负责业务编排、
HTTP 路由或前端告警展示。
"""

from __future__ import annotations

import asyncio
import enum
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from src.config import config

logger = logging.getLogger("kagent.core.protection")


# ── 熔断器状态 ──────────────────────────────────────────────────

class CircuitState(enum.Enum):
    """熔断器三态机。"""
    CLOSED = "closed"        # 正常：所有请求通过
    OPEN = "open"            # 熔断：所有请求被拦截
    HALF_OPEN = "half_open"  # 半开：允许少量请求探测恢复


# ── 熔断器 ──────────────────────────────────────────────────────

@dataclass
class CircuitBreaker:
    """轻量级高性能熔断器。

    状态流转：
        CLOSED ──(连续N次失败)──→ OPEN ──(超时)──→ HALF_OPEN ──(成功)──→ CLOSED
                                                  HALF_OPEN ──(失败)──→ OPEN

    监控目标：下游大模型 API 的 5xx / 429 / TimeoutError。
    熔断行为：OPEN 状态下拦截所有请求，返回降级提示，保护上游防雪崩。
    """

    name: str = "llm_api"
    failure_threshold: int = field(default_factory=lambda: config.circuit_breaker_threshold)
    recovery_timeout: int = field(default_factory=lambda: config.circuit_breaker_timeout)
    half_open_max_calls: int = 3

    # 内部状态
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False, repr=False)
    _failure_count: int = field(default=0, init=False, repr=False)
    _success_count: int = field(default=0, init=False, repr=False)
    _last_failure_time: float = field(default=0.0, init=False, repr=False)
    _half_open_calls: int = field(default=0, init=False, repr=False)

    # 统计
    _total_requests: int = field(default=0, init=False, repr=False)
    _total_failures: int = field(default=0, init=False, repr=False)
    _total_rejected: int = field(default=0, init=False, repr=False)

    # ── 状态属性 ────────────────────────────────────────────────

    @property
    def state(self) -> CircuitState:
        """获取当前状态（自动检查 OPEN → HALF_OPEN 转换）。"""
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self.recovery_timeout:
                logger.info(
                    "熔断器 %s: OPEN → HALF_OPEN (已过 %.0fs)",
                    self.name, elapsed,
                )
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
        return self._state

    @property
    def is_closed(self) -> bool:
        """是否处于允许通过状态（CLOSED 或 HALF_OPEN 且未满额）。"""
        s = self.state
        if s == CircuitState.CLOSED:
            return True
        if s == CircuitState.HALF_OPEN and self._half_open_calls < self.half_open_max_calls:
            return True
        return False

    # ── 核心方法 ────────────────────────────────────────────────

    def record_success(self) -> None:
        """记录一次成功调用。"""
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            self._half_open_calls = max(0, self._half_open_calls - 1)
            if self._success_count >= self.half_open_max_calls:
                logger.info("熔断器 %s: HALF_OPEN → CLOSED (连续 %d 次成功)", self.name, self._success_count)
                self._reset()
        elif self._state == CircuitState.CLOSED:
            self._failure_count = 0

    def record_failure(self, exc: Exception | None = None) -> None:
        """记录一次失败调用（5xx / 429 / TimeoutError）。"""
        self._total_failures += 1
        self._failure_count += 1
        self._last_failure_time = time.monotonic()

        exc_name = type(exc).__name__ if exc else "unknown"
        logger.warning(
            "熔断器 %s: 记录失败 #%d/%d (type=%s)",
            self.name, self._failure_count, self.failure_threshold, exc_name,
        )

        if self._state == CircuitState.HALF_OPEN:
            logger.warning("熔断器 %s: HALF_OPEN → OPEN (探测失败)", self.name)
            self._state = CircuitState.OPEN
            self._success_count = 0
            self._half_open_calls = 0
        elif self._failure_count >= self.failure_threshold:
            logger.error(
                "🔥 熔断器 %s: CLOSED → OPEN (连续 %d 次失败，熔断 %ds)",
                self.name, self._failure_count, self.recovery_timeout,
            )
            self._state = CircuitState.OPEN

    def allow_request(self) -> bool:
        """检查是否允许通过请求。"""
        self._total_requests += 1
        if self.is_closed:
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_calls += 1
            return True

        self._total_rejected += 1
        elapsed = time.monotonic() - self._last_failure_time
        remaining = max(0, self.recovery_timeout - elapsed)
        logger.warning(
            "🚫 熔断器 %s: 请求被拦截 (OPEN，剩余 %.0fs 恢复倒计时)",
            self.name, remaining,
        )
        return False

    # ── 重置 ────────────────────────────────────────────────────

    def _reset(self) -> None:
        """重置为 CLOSED 状态。"""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0

    def force_open(self) -> None:
        """手动强制开启熔断（运维接口）。"""
        self._state = CircuitState.OPEN
        self._last_failure_time = time.monotonic()
        logger.warning("熔断器 %s: 手动强制 OPEN", self.name)

    def force_close(self) -> None:
        """手动强制关闭熔断（运维接口）。"""
        self._reset()
        logger.info("熔断器 %s: 手动强制 CLOSED", self.name)

    # ── 统计 ────────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        """返回熔断器统计信息。"""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
            "total_requests": self._total_requests,
            "total_failures": self._total_failures,
            "total_rejected": self._total_rejected,
        }

    # ── 上下文管理器 ────────────────────────────────────────────

    async def __aenter__(self) -> CircuitBreaker:
        """异步上下文管理器：进入时检查是否允许。"""
        if not self.allow_request():
            raise CircuitBreakerOpenError(
                f"熔断器 {self.name} 已开启，请求被拦截。"
                f"恢复倒计时: {max(0, self.recovery_timeout - (time.monotonic() - self._last_failure_time)):.0f}s"
            )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        """异步上下文管理器：退出时记录结果。"""
        if exc_type is None:
            self.record_success()
        else:
            self.record_failure(exc_val)
        return False  # 不吞异常


# ── 熔断异常 ────────────────────────────────────────────────────

class CircuitBreakerOpenError(Exception):
    """熔断器开启状态下的拦截异常。"""


# ── 全局熔断器单例 ──────────────────────────────────────────────

llm_circuit_breaker = CircuitBreaker(name="llm_api")
