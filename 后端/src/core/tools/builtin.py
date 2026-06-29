"""KAgent 内置 Agent 工具。"""

from __future__ import annotations

import ast
import math
from typing import Any, Awaitable, Callable, Optional

from src.core.tools.registry import tool

KnowledgeQueryHandler = Callable[..., Awaitable[tuple[list[Any], dict[str, Any]]]]
_knowledge_query_handler: Optional[KnowledgeQueryHandler] = None


def configure_knowledge_query(handler: KnowledgeQueryHandler) -> None:
    """注入应用层 RAG 检索函数。"""
    global _knowledge_query_handler
    _knowledge_query_handler = handler


@tool(name="query_knowledge", description="检索企业内部知识库，获取与问题相关的文档片段")
async def query_knowledge(
    query: str,
    tenant_id: str = "default_tenant",
    department: str = "general",
) -> str:
    """检索企业知识库，并返回可供 LLM 使用的文档片段。"""
    if _knowledge_query_handler is None:
        return "知识库检索服务未配置"
    results, _metrics = await _knowledge_query_handler(
        query=query,
        tenant_id=tenant_id,
        department=department,
        top_k=3,
    )
    if not results:
        return "未检索到相关企业知识"
    return "\n".join(
        f"[{index}] {result.text}"
        for index, result in enumerate(results, start=1)
    )


@tool(name="web_search", description="搜索互联网获取实时信息")
async def web_search(query: str) -> str:
    """返回互联网搜索的模拟结果。"""
    return f"[模拟网络搜索结果] {query}"


_CALCULATOR_NAMES: dict[str, Any] = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "pi": math.pi,
    "e": math.e,
    "sqrt": math.sqrt,
    "pow": pow,
}
_ALLOWED_AST_NODES = (
    ast.Expression,
    ast.Constant,
    ast.List,
    ast.Tuple,
    ast.BinOp,
    ast.UnaryOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.UAdd,
    ast.USub,
    ast.Call,
    ast.Name,
    ast.Load,
)


def _validate_expression(expression: str) -> ast.Expression:
    """验证表达式仅包含允许的数学语法。"""
    parsed = ast.parse(expression, mode="eval")
    for node in ast.walk(parsed):
        if not isinstance(node, _ALLOWED_AST_NODES):
            raise ValueError(f"不允许的表达式语法: {type(node).__name__}")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float)):
            raise ValueError("只允许数字常量")
        if isinstance(node, ast.Name) and node.id not in _CALCULATOR_NAMES:
            raise ValueError(f"不允许的名称: {node.id}")
        if isinstance(node, ast.Call) and not isinstance(node.func, ast.Name):
            raise ValueError("只允许调用白名单函数")
    return parsed


@tool(name="calculator", description="执行数学计算，支持 +-*/ 和括号")
async def calculator(expression: str) -> str:
    """在受限环境中计算数学表达式。"""
    try:
        parsed = _validate_expression(expression)
        result = eval(compile(parsed, "<calculator>", "eval"), {"__builtins__": {}}, _CALCULATOR_NAMES)
        return f"计算结果: {result}"
    except Exception as exc:
        return f"计算失败: {exc}"
