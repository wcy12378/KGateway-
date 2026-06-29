"""LLM Provider 的统一抽象接口。"""

from abc import ABC, abstractmethod
from typing import AsyncGenerator, Optional


class LLMProvider(ABC):
    """定义不同 LLM 服务商必须实现的聊天能力。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """返回 Provider 的唯一名称。"""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: Optional[list[dict]] = None,
    ) -> dict:
        """非流式调用，返回内容、token 用量和工具调用。"""

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        """流式调用，逐段产出模型文本。"""

    @abstractmethod
    def get_models(self) -> list[str]:
        """返回当前 Provider 可用的模型。"""
