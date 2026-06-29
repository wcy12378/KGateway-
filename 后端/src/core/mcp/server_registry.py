"""MCP Server 注册中心。

本模块管理多个 MCP Server 的生命周期，并将远程工具注册到 KAgent 的
ToolRegistry。连接失败由应用启动层降级处理。
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any, Dict, List

from src.core.mcp.client import MCPClient
from src.core.tools.registry import Tool, ToolSpec, get_registry

logger = logging.getLogger("kagent.mcp.registry")


def _agent_tool_name(server_name: str, tool_name: str) -> str:
    """生成符合主流 LLM function calling 约束的唯一工具名。"""
    raw = f"mcp_{server_name}_{tool_name}"
    normalized = re.sub(r"[^a-zA-Z0-9_-]", "_", raw)
    if len(normalized) <= 64:
        return normalized
    suffix = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
    return f"{normalized[:55]}_{suffix}"


def _make_handler(client: MCPClient, method_name: str):
    """为单个 MCP 工具创建参数透传 handler。"""

    async def handler(**kwargs: Any) -> str:
        return await client.call_tool(method_name, kwargs)

    return handler


class MCPServerRegistry:
    """管理 MCP Server 的注册、工具发现和注销。"""

    def __init__(self) -> None:
        self._clients: Dict[str, MCPClient] = {}
        self._tool_names: Dict[str, List[str]] = {}

    async def register_server(
        self,
        name: str,
        command: str,
        args: List[str] | None = None,
    ) -> None:
        """连接 Server，发现工具并注入全局 ToolRegistry。"""
        if name in self._clients:
            logger.warning("MCP Server '%s' 已注册，跳过", name)
            return

        client = MCPClient(name, command, args or [])
        registered_names: List[str] = []
        registry = get_registry()
        try:
            await client.connect()
            for mcp_tool in await client.list_tools():
                tool_name = _agent_tool_name(name, mcp_tool.name)
                if registry.get(tool_name) is not None:
                    raise ValueError(f"MCP 工具名冲突: {tool_name}")
                description = f"[MCP/{name}] {mcp_tool.description}"
                registry.register(
                    Tool(
                        name=tool_name,
                        description=description,
                        fn=_make_handler(client, mcp_tool.name),
                        spec=ToolSpec(
                            name=tool_name,
                            description=description,
                            parameters=mcp_tool.parameters,
                        ),
                    )
                )
                registered_names.append(tool_name)
        except Exception:
            for tool_name in registered_names:
                registry.unregister(tool_name)
            await client.close()
            raise

        self._clients[name] = client
        self._tool_names[name] = registered_names
        logger.info(
            "MCP Server '%s' 注册完成，发现 %d 个工具",
            name,
            len(registered_names),
        )

    async def close_all(self) -> None:
        """注销 MCP 工具并断开全部 Server。"""
        registry = get_registry()
        for tool_names in self._tool_names.values():
            for tool_name in tool_names:
                registry.unregister(tool_name)
        self._tool_names.clear()

        for name, client in list(self._clients.items()):
            try:
                await client.close()
            except Exception as exc:
                logger.warning("MCP Server '%s' 关闭异常: %s", name, exc)
        self._clients.clear()


_registry = MCPServerRegistry()


def get_mcp_registry() -> MCPServerRegistry:
    """返回全局 MCP Server 注册中心。"""
    return _registry
