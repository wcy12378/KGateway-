"""Google Gemini Generative Language API Provider 实现。"""

from __future__ import annotations

import json
from typing import AsyncGenerator, Optional
from urllib.parse import quote

import httpx

from src.core.providers.base import LLMProvider


def _text_content(content: object) -> str:
    """把 OpenAI 消息内容转换为 Gemini 文本 part。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    return str(content or "")


def _convert_messages(messages: list[dict]) -> tuple[list[dict], dict | None]:
    """将 OpenAI 消息格式转换为 Gemini contents 格式。"""
    system_parts: list[dict] = []
    contents: list[dict] = []
    for message in messages:
        text = _text_content(message.get("content", ""))
        if message.get("role") == "system":
            system_parts.append({"text": text})
            continue
        if message.get("role") == "tool":
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": {
                                "name": message.get("name", "unknown_tool"),
                                "response": {"result": text},
                            }
                        }
                    ],
                }
            )
            continue
        role = "model" if message.get("role") == "assistant" else "user"
        parts: list[dict] = []
        if text:
            parts.append({"text": text})
        for tool_call in message.get("tool_calls") or []:
            function = tool_call.get("function", {})
            arguments = function.get("arguments", {})
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {}
            parts.append(
                {
                    "functionCall": {
                        "name": function.get("name", ""),
                        "args": arguments,
                    }
                }
            )
        if parts:
            contents.append({"role": role, "parts": parts})
    system_instruction = {"parts": system_parts} if system_parts else None
    return contents, system_instruction


def _fallback_text(messages: list[dict]) -> str:
    """提取最后一条用户消息作为无 Key 时的降级内容。"""
    for message in reversed(messages):
        if message.get("role") == "user":
            return _text_content(message.get("content", ""))
    return "LLM Provider 未配置 API Key。"


class GeminiProvider(LLMProvider):
    """通过 Google Generative Language API 提供聊天能力。"""

    api_base = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, config: object) -> None:
        super().__init__(config)

    @property
    def name(self) -> str:
        return "gemini"

    def get_models(self) -> list[str]:
        return [self.config.gemini_model]

    def _url(self, model: str, *, stream: bool) -> str:
        method = "streamGenerateContent?alt=sse" if stream else "generateContent"
        return f"{self.api_base}/{quote(model, safe='')}:{method}"

    def _headers(self) -> dict[str, str]:
        """通过请求头传递密钥，避免密钥出现在 URL 和访问日志中。"""
        return {"x-goog-api-key": self.config.gemini_api_key}

    @staticmethod
    def _payload(
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        tools: Optional[list[dict]] = None,
    ) -> dict:
        contents, system_instruction = _convert_messages(messages)
        payload = {
            "contents": contents,
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }
        if system_instruction is not None:
            payload["system_instruction"] = system_instruction
        if tools:
            payload["tools"] = [
                {
                    "functionDeclarations": [
                        {
                            "name": item["function"]["name"],
                            "description": item["function"].get("description", ""),
                            "parameters": item["function"].get("parameters", {"type": "object", "properties": {}}),
                        }
                        for item in tools
                        if item.get("type") == "function" and item.get("function")
                    ]
                }
            ]
        return payload

    async def chat(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: Optional[list[dict]] = None,
    ) -> dict:
        if not self.config.gemini_api_key:
            return {"content": _fallback_text(messages), "input_tokens": 0, "output_tokens": 0, "tool_calls": []}

        selected_model = model or self.config.gemini_model
        response = await self.client.post(
            self._url(selected_model, stream=False),
            headers=self._headers(),
            json=self._payload(messages, temperature, max_tokens, tools),
        )
        response.raise_for_status()
        data = response.json()
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        usage = data.get("usageMetadata", {})
        tool_calls = [part["functionCall"] for part in parts if "functionCall" in part]
        return {
            "content": "".join(part.get("text", "") for part in parts),
            "input_tokens": usage.get("promptTokenCount", 0),
            "output_tokens": usage.get("candidatesTokenCount", 0),
            "tool_calls": tool_calls,
        }

    async def chat_stream(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        if not self.config.gemini_api_key:
            from src.application.streaming_tasks import simulate_llm_tokens

            async for chunk in simulate_llm_tokens(_fallback_text(messages)):
                yield chunk
            return

        selected_model = model or self.config.gemini_model
        async with self.client.stream(
            "POST",
            self._url(selected_model, stream=True),
            headers=self._headers(),
            json=self._payload(messages, temperature, max_tokens),
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                try:
                    data = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                for part in parts:
                    if part.get("text"):
                        yield part["text"]
