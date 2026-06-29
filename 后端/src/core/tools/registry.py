"""Agent 工具注册表与装饰器。"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, get_type_hints


@dataclass
class ToolSpec:
    """工具名称、描述与参数 JSON Schema。"""

    name: str
    description: str
    parameters: Dict[str, Any]


@dataclass
class Tool:
    """可执行工具及其对外规范。"""

    name: str
    description: str
    fn: Callable[..., Any]
    spec: ToolSpec

    def to_openai_tool(self) -> Dict[str, Any]:
        """转换为 OpenAI function tool 格式。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.spec.parameters,
            },
        }


class ToolRegistry:
    """按名称保存和查询 Agent 工具。"""

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, registered_tool: Tool) -> None:
        """注册工具；同名工具以最新注册为准。"""
        self._tools[registered_tool.name] = registered_tool

    def get(self, name: str) -> Optional[Tool]:
        """按名称获取工具。"""
        return self._tools.get(name)

    def unregister(self, name: str) -> Optional[Tool]:
        """注销并返回指定工具；不存在时返回 None。"""
        return self._tools.pop(name, None)

    def get_all(self) -> List[Tool]:
        """按注册顺序返回全部工具。"""
        return list(self._tools.values())

    def to_openai_tools(self) -> List[Dict[str, Any]]:
        """返回 OpenAI function tools 列表。"""
        return [registered_tool.to_openai_tool() for registered_tool in self.get_all()]


_registry = ToolRegistry()


def get_registry() -> ToolRegistry:
    """返回全局工具注册表。"""
    return _registry


def _json_type(annotation: Any) -> str:
    """把基础 Python 类型转换为 JSON Schema 类型。"""
    return {str: "string", int: "integer", float: "number", bool: "boolean"}.get(annotation, "string")


def tool(name: Optional[str] = None, description: Optional[str] = None) -> Callable:
    """把异步函数注册为 Agent 工具，并从签名生成参数规范。"""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        signature = inspect.signature(fn)
        try:
            type_hints = get_type_hints(fn)
        except (NameError, TypeError):
            type_hints = {}

        properties: Dict[str, Any] = {}
        required: List[str] = []
        for parameter_name, parameter in signature.parameters.items():
            annotation = type_hints.get(parameter_name, parameter.annotation)
            properties[parameter_name] = {"type": _json_type(annotation)}
            if parameter.default is inspect.Parameter.empty:
                required.append(parameter_name)
            else:
                properties[parameter_name]["default"] = parameter.default

        tool_name = name or fn.__name__
        tool_description = description or inspect.getdoc(fn) or ""
        parameters: Dict[str, Any] = {
            "type": "object",
            "properties": properties,
            "additionalProperties": False,
        }
        if required:
            parameters["required"] = required
        spec = ToolSpec(name=tool_name, description=tool_description, parameters=parameters)
        _registry.register(Tool(name=tool_name, description=tool_description, fn=fn, spec=spec))
        return fn

    return decorator
