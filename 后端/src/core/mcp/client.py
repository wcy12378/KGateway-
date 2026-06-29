"""MCP 协议客户端。

本模块使用官方 MCP Python SDK 连接 stdio Server，负责初始化、工具发现
和工具调用。它不负责注册到 KAgent 工具系统。
"""

from __future__ import annotations

import json
import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any, Dict, List

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger("kagent.mcp.client")


@dataclass
class MCPToolSpec:
    """MCP Server 暴露的工具描述。"""

    name: str
    description: str
    parameters: Dict[str, Any]


class MCPClient:
    """通过官方 SDK 管理单个 stdio MCP Server 会话。"""

    def __init__(self, server_name: str, command: str, args: List[str] | None = None) -> None:
        self.server_name = server_name
        self.command = command
        self.args = args or []
        self._exit_stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._capabilities: Any = None

    @property
    def connected(self) -> bool:
        """返回 MCP 会话是否已初始化。"""
        return self._session is not None

    async def connect(self) -> None:
        """启动 MCP Server 子进程并完成官方初始化握手。"""
        if self.connected:
            return

        stack = AsyncExitStack()
        try:
            server_params = StdioServerParameters(
                command=self.command,
                args=self.args,
            )
            read_stream, write_stream = await stack.enter_async_context(
                stdio_client(server_params)
            )
            session = await stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            initialization = await session.initialize()
        except Exception:
            await stack.aclose()
            raise

        self._exit_stack = stack
        self._session = session
        self._capabilities = initialization.capabilities
        logger.info(
            "MCP Server '%s' 已连接，能力: %s",
            self.server_name,
            self._capabilities,
        )

    def _require_session(self) -> ClientSession:
        if self._session is None:
            raise RuntimeError(f"MCP Server '{self.server_name}' 尚未连接")
        return self._session

    async def list_tools(self) -> List[MCPToolSpec]:
        """获取 MCP Server 暴露的工具列表。"""
        result = await self._require_session().list_tools()
        return [
            MCPToolSpec(
                name=item.name,
                description=item.description or "",
                parameters=item.inputSchema,
            )
            for item in result.tools
        ]

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        """调用 MCP 工具，并把文本或结构化结果转换为字符串。"""
        result = await self._require_session().call_tool(name, arguments)
        texts = [
            str(item.text)
            for item in result.content
            if getattr(item, "type", None) == "text" and hasattr(item, "text")
        ]
        structured = getattr(result, "structuredContent", None)
        if not texts and structured is not None:
            texts.append(json.dumps(structured, ensure_ascii=False, default=str))
        output = "\n".join(part for part in texts if part)
        if result.isError:
            raise RuntimeError(output or f"MCP 工具 '{name}' 调用失败")
        return output

    async def close(self) -> None:
        """关闭 MCP 会话和 Server 子进程。"""
        stack = self._exit_stack
        self._session = None
        self._exit_stack = None
        self._capabilities = None
        if stack is not None:
            await stack.aclose()
            logger.info("MCP Server '%s' 已断开", self.server_name)
