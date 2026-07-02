"""LLM Provider 的懒加载、健康追踪与自动 fallback。"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, AsyncGenerator

from src.core.providers.base import LLMProvider, ProviderHealth

logger = logging.getLogger("kagent.core.providers.factory")

PROVIDER_NAMES = ("deepseek", "openai", "gemini")
FAILURE_THRESHOLD = 3


class ProviderUnavailableError(RuntimeError):
    """所有已配置 Provider 均不可用。"""


class ProviderFactory:
    """按策略选择 Provider，并在调用失败时自动切换。"""

    def __init__(self) -> None:
        self._config: Any = None
        self._providers: dict[str, LLMProvider] = {}

    def init(self, config: Any) -> None:
        """传入运行配置，并清空此前缓存和健康状态。"""
        if self._providers:
            raise RuntimeError("ProviderFactory 重新初始化前必须先 await close()")
        self._config = config

    def _has_api_key(self, name: str) -> bool:
        return self._config is not None and bool(getattr(self._config, f"{name}_api_key", ""))

    def _create_provider(self, name: str) -> LLMProvider | None:
        if name == "deepseek":
            from src.core.providers.deepseek import DeepSeekProvider

            return DeepSeekProvider(self._config)
        if name == "openai":
            from src.core.providers.openai import OpenAIProvider

            return OpenAIProvider(self._config)
        if name == "gemini":
            from src.core.providers.gemini import GeminiProvider

            return GeminiProvider(self._config)
        logger.warning("未知 LLM Provider: %s", name)
        return None

    def _get(self, name: str) -> LLMProvider | None:
        normalized = name.strip().lower()
        if normalized not in PROVIDER_NAMES or not self._has_api_key(normalized):
            return None
        if normalized not in self._providers:
            provider = self._create_provider(normalized)
            if provider is None:
                return None
            self._providers[normalized] = provider
        return self._providers[normalized]

    def _priority_names(self, preferred: str | None = None) -> list[str]:
        configured_default = str(getattr(self._config, "kagent_llm_provider", "deepseek")).strip().lower()
        names: list[str] = []
        for name in (preferred, configured_default, *PROVIDER_NAMES):
            if name and name in PROVIDER_NAMES and name not in names:
                names.append(name)
        return names

    @staticmethod
    def _reserve_recovery_probe(provider: LLMProvider) -> bool:
        if provider.recovery_probe_in_flight:
            return False
        if provider.ready_for_probe():
            provider.recovery_probe_in_flight = True
            provider.health = ProviderHealth.DEGRADED
            provider.consecutive_failures = FAILURE_THRESHOLD - 1
            logger.info("Provider '%s' 隔离期结束，允许恢复探测", provider.name)
            return True
        return provider.health != ProviderHealth.UNHEALTHY

    def get_provider_candidates(
        self,
        preferred: str | None = None,
        *,
        exclude: set[str] | None = None,
        reserve_recovery_probe: bool = False,
    ) -> list[LLMProvider]:
        """按健康度和路由策略返回本次调用的候选列表。"""
        if self._config is None:
            logger.warning("ProviderFactory 尚未初始化")
            return []

        excluded = exclude or set()
        priority_names = self._priority_names(preferred)
        providers: list[LLMProvider] = []
        for name in priority_names:
            if name in excluded:
                continue
            provider = self._get(name)
            if provider is None:
                continue
            if reserve_recovery_probe and not self._reserve_recovery_probe(provider):
                continue
            if provider.health != ProviderHealth.UNHEALTHY:
                providers.append(provider)

        priority_index = {name: index for index, name in enumerate(priority_names)}
        health_rank = {
            ProviderHealth.HEALTHY: 0,
            ProviderHealth.DEGRADED: 1,
            ProviderHealth.UNHEALTHY: 2,
        }
        strategy = str(getattr(self._config, "provider_routing_strategy", "priority")).lower()
        if strategy == "latency":
            providers.sort(
                key=lambda provider: (
                    health_rank[provider.health],
                    provider.avg_latency_ms if provider.avg_latency_ms is not None else float("inf"),
                    priority_index[provider.name],
                )
            )
        else:
            if strategy != "priority":
                logger.warning("未知 Provider 路由策略 '%s'，回退为 priority", strategy)
            providers.sort(key=lambda provider: priority_index[provider.name])
        return providers

    def get_provider(self, name: str | None = None) -> LLMProvider | None:
        """返回最优可用 Provider；指定 Provider 不健康时自动 fallback。"""
        candidates = self.get_provider_candidates(name)
        if name and (not candidates or candidates[0].name != name.strip().lower()):
            logger.warning("Provider '%s' 不可用，尝试 fallback", name)
        return candidates[0] if candidates else None

    def get_all_providers(self) -> list[LLMProvider]:
        """返回所有已配置 Provider，包括暂时不健康的实例。"""
        if self._config is None:
            return []
        return [provider for name in self._priority_names() if (provider := self._get(name)) is not None]

    async def close(self) -> None:
        await asyncio.gather(
            *(provider.close() for provider in self._providers.values()),
            return_exceptions=True,
        )
        self._providers.clear()

    def record_success(self, provider_name: str, latency_ms: float = 0.0) -> None:
        provider = self._get(provider_name)
        if provider is None:
            return
        provider.consecutive_failures = 0
        provider.health = ProviderHealth.HEALTHY
        provider.recovery_probe_in_flight = False
        if latency_ms > 0:
            provider.avg_latency_ms = (
                latency_ms
                if provider.avg_latency_ms is None
                else provider.avg_latency_ms * 0.7 + latency_ms * 0.3
            )

    def record_failure(self, provider_name: str) -> None:
        provider = self._get(provider_name)
        if provider is None:
            return
        provider.consecutive_failures += 1
        provider.last_failure_time = time.monotonic()
        provider.recovery_probe_in_flight = False
        if provider.consecutive_failures >= FAILURE_THRESHOLD:
            provider.health = ProviderHealth.UNHEALTHY
            logger.warning(
                "Provider '%s' 已隔离（连续 %d 次失败）",
                provider.name,
                provider.consecutive_failures,
            )
        else:
            provider.health = ProviderHealth.DEGRADED

    async def chat_with_fallback(
        self,
        messages: list[dict],
        *,
        preferred: str | None = None,
        **kwargs: Any,
    ) -> dict:
        """依次调用候选 Provider，直到获得有效响应。"""
        errors: list[tuple[str, Exception]] = []
        for provider in self.get_provider_candidates(preferred, reserve_recovery_probe=True):
            started_at = time.perf_counter()
            try:
                response = await provider.chat(messages, **kwargs)
                if not isinstance(response, dict):
                    raise TypeError(f"Provider 返回了非对象响应: {type(response).__name__}")
                response.setdefault("provider", provider.name)
                configured_models = provider.get_models()
                response.setdefault(
                    "model",
                    kwargs.get("model") or (configured_models[0] if configured_models else ""),
                )
                self.record_success(provider.name, (time.perf_counter() - started_at) * 1000)
                return response
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.record_failure(provider.name)
                errors.append((provider.name, exc))
                logger.warning("Provider '%s' 调用失败，尝试 fallback: %s", provider.name, exc)

        names = ", ".join(name for name, _ in errors) or "none"
        raise ProviderUnavailableError(f"所有 Provider 均不可用（已尝试: {names}）")

    async def chat_stream_with_fallback(
        self,
        messages: list[dict],
        *,
        preferred: str | None = None,
        on_provider_selected: Any = None,
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """在首个 chunk 前失败时切换 Provider；输出后失败则终止以防混流。"""
        errors: list[tuple[str, Exception]] = []
        for provider in self.get_provider_candidates(preferred, reserve_recovery_probe=True):
            started_at = time.perf_counter()
            emitted = False
            try:
                async for chunk in provider.chat_stream(messages, **kwargs):
                    if not emitted and callable(on_provider_selected):
                        models = provider.get_models()
                        on_provider_selected(
                            provider.name,
                            kwargs.get("model") or (models[0] if models else ""),
                        )
                    emitted = True
                    yield chunk
                if not emitted:
                    raise RuntimeError("Provider 未返回任何流式内容")
                self.record_success(provider.name, (time.perf_counter() - started_at) * 1000)
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.record_failure(provider.name)
                if emitted:
                    logger.error("Provider '%s' 流式输出中断，拒绝混合 fallback 响应", provider.name)
                    raise
                errors.append((provider.name, exc))
                logger.warning("Provider '%s' 流式调用失败，尝试 fallback: %s", provider.name, exc)

        names = ", ".join(name for name, _ in errors) or "none"
        raise ProviderUnavailableError(f"所有 Provider 均不可用（已尝试: {names}）")
