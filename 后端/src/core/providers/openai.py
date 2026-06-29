"""OpenAI Chat Completions Provider 实现。"""

from __future__ import annotations

import json
from typing import AsyncGenerator, Optional

import httpx

from src.core.providers.base import LLMProvider


def _fallback_text(messages: list[dict]) -> str:
    """提取最后一条用户消息作为无 Key 时的降级内容。"""
    for message in reversed(messages):
        if message.get("role") == "user":
            return str(message.get("content", ""))
    return "LLM Provider 未配置 API Key。"


class OpenAIProvider(LLMProvider):
    """通过 OpenAI Chat Completions API 提供聊天能力。"""

    def __init__(self, config: object) -> None:
        self.config = config

    @property
    def name(self) -> str:
        return "openai"

    def get_models(self) -> list[str]:
        return [self.config.openai_model]

    async def chat(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: Optional[list[dict]] = None,
    ) -> dict:
        if not self.config.openai_api_key:
            return {"content": _fallback_text(messages), "input_tokens": 0, "output_tokens": 0, "tool_calls": []}

        payload = {
            "model": model or self.config.openai_model,
            "messages": messages,
            "stream": False,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
        headers = {"Authorization": f"Bearer {self.config.openai_api_key}"}
        async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=10)) as client:
            response = await client.post(self.config.openai_api_url, headers=headers, json=payload)
            response.raise_for_status()
        data = response.json()
        message = data.get("choices", [{}])[0].get("message", {})
        usage = data.get("usage", {})
        return {
            "content": message.get("content") or "",
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
            "tool_calls": message.get("tool_calls") or [],
        }

    async def chat_stream(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        if not self.config.openai_api_key:
            from src.application.streaming_tasks import simulate_llm_tokens

            async for chunk in simulate_llm_tokens(_fallback_text(messages)):
                yield chunk
            return

        payload = {
            "model": model or self.config.openai_model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {"Authorization": f"Bearer {self.config.openai_api_key}"}
        async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=10)) as client:
            async with client.stream("POST", self.config.openai_api_url, headers=headers, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    raw = line[6:]
                    if raw == "[DONE]":
                        break
                    try:
                        delta = json.loads(raw).get("choices", [{}])[0].get("delta", {})
                    except json.JSONDecodeError:
                        continue
                    content = delta.get("content")
                    if content:
                        yield content
