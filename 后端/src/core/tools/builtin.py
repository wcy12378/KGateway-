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
_MAX_EXPRESSION_LENGTH = 512
_MAX_AST_NODES = 128
_MAX_INTEGER_ABS = 10**12
_MAX_POWER_EXPONENT = 10_000
_MAX_COLLECTION_MULTIPLIER = 10_000


def _validate_expression(expression: str) -> ast.Expression:
    """验证表达式仅包含允许的数学语法。"""
    if len(expression) > _MAX_EXPRESSION_LENGTH:
        raise ValueError("表达式规模超过限制")
    parsed = ast.parse(expression, mode="eval")
    nodes = list(ast.walk(parsed))
    if len(nodes) > _MAX_AST_NODES:
        raise ValueError("表达式规模超过限制")
    for node in nodes:
        if not isinstance(node, _ALLOWED_AST_NODES):
            raise ValueError(f"不允许的表达式语法: {type(node).__name__}")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float)):
            raise ValueError("只允许数字常量")
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            if abs(node.value) > _MAX_INTEGER_ABS:
                raise ValueError("整数规模超过限制")
        if isinstance(node, ast.Name) and node.id not in _CALCULATOR_NAMES:
            raise ValueError(f"不允许的名称: {node.id}")
        if isinstance(node, ast.Call) and not isinstance(node.func, ast.Name):
            raise ValueError("只允许调用白名单函数")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "pow"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, int)
            and abs(node.args[1].value) > _MAX_POWER_EXPONENT
        ):
            raise ValueError("幂运算规模超过限制")
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
            operands = ((node.left, node.right), (node.right, node.left))
            if any(
                isinstance(collection, (ast.List, ast.Tuple))
                and isinstance(multiplier, ast.Constant)
                and isinstance(multiplier.value, int)
                and multiplier.value > _MAX_COLLECTION_MULTIPLIER
                for collection, multiplier in operands
            ):
                raise ValueError("容器运算规模超过限制")
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
