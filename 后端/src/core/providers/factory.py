"""LLM Provider 的懒加载工厂。"""

from __future__ import annotations

import logging
from typing import Any

from src.core.providers.base import LLMProvider

logger = logging.getLogger("kagent.core.providers.factory")


class ProviderFactory:
    """按配置懒加载 Provider，并在进程内复用实例。"""

    def __init__(self) -> None:
        self._config: Any = None
        self._providers: dict[str, LLMProvider] = {}

    def init(self, config: Any) -> None:
        """传入运行配置，并清空此前缓存的 Provider。"""
        self._config = config
        self._providers: dict[str, LLMProvider] = {}

    def _has_api_key(self, name: str) -> bool:
        return bool(getattr(self._config, f"{name}_api_key", ""))

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

    def get_provider(self, name: str | None = None) -> LLMProvider | None:
        """返回指定或默认 Provider；未配置 API Key 时返回 None。"""
        if self._config is None:
            logger.warning("ProviderFactory 尚未初始化")
            return None
        selected = (name or self._config.kagent_llm_provider).strip().lower()
        if not self._has_api_key(selected):
            return None
        if selected not in self._providers:
            provider = self._create_provider(selected)
            if provider is None:
                return None
            self._providers[selected] = provider
        return self._providers[selected]

    def get_all_providers(self) -> list[LLMProvider]:
        """返回所有已配置 API Key 的 Provider。"""
        providers: list[LLMProvider] = []
        for name in ("deepseek", "openai", "gemini"):
            provider = self.get_provider(name)
            if provider is not None:
                providers.append(provider)
        return providers
