"""LLM 驱动的 ReAct Tool Calling Agent。"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.core.schemas import GatewayRequest
from src.core.tools.registry import ToolRegistry, get_registry

logger = logging.getLogger("kagent.core.agent.react_agent")

SYSTEM_PROMPT_TEMPLATE = """你是一个企业级 AI 助手，可以调用以下工具来帮助用户解决问题。

可用工具：
{tools_description}

工作流程：
1. 分析用户问题，决定是否需要调用工具
2. 如果需要工具，请调用工具获取信息
3. 根据工具返回结果，给出最终答案
4. 如果不需要工具，可以直接回答
"""


@dataclass
class ReActStep:
    """一次工具调用的思考、动作和观察记录。"""

    thought: str = ""
    action: str = ""
    action_input: Dict[str, Any] = field(default_factory=dict)
    observation: str = ""
    duration_ms: float = 0.0


@dataclass
class ReActResult:
    """ReAct 执行的最终答案与完整轨迹。"""

    answer: str = ""
    steps: List[ReActStep] = field(default_factory=list)
    total_duration_ms: float = 0.0
    total_tokens: int = 0


@dataclass
class AgentState:
    """保持现有编排层兼容的 Agent 执行状态。"""

    request: GatewayRequest
    history: List[Dict[str, str]] = field(default_factory=list)
    steps: List[Dict[str, Any]] = field(default_factory=list)
    next_node: str = "planner_node"
    final_answer: str = ""
    rag_context: str = ""
    iteration: int = 0
    max_iterations: int = 4

    def snapshot(self) -> Dict[str, Any]:
        """返回用于观测的轻量状态快照。"""
        return {
            "iteration": self.iteration,
            "next_node": self.next_node,
            "steps_count": len(self.steps),
            "has_rag_context": bool(self.rag_context),
            "final_answer_len": len(self.final_answer),
        }


def _normalize_tool_call(
    raw_call: Dict[str, Any],
    index: int,
    *,
    call_id_prefix: str = "call",
) -> tuple[Dict[str, Any], str, Dict[str, Any]]:
    """把 Gemini 或 OpenAI 格式的工具调用统一为 OpenAI 格式。"""
    if not isinstance(raw_call, dict):
        raise ValueError("tool_call 必须是对象")

    if isinstance(raw_call.get("function"), dict):
        function = raw_call["function"]
        name = str(function.get("name", "")).strip()
        arguments = function.get("arguments", {})
        call_id = str(raw_call.get("id") or f"{call_id_prefix}_{index}")
    else:
        name = str(raw_call.get("name", "")).strip()
        arguments = raw_call.get("args", {})
        call_id = str(raw_call.get("id") or f"{call_id_prefix}_{index}")

    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError as exc:
            raise ValueError(f"工具参数不是有效 JSON: {exc.msg}") from exc
    if not isinstance(arguments, dict):
        raise ValueError("工具参数必须是对象")
    if not name:
        raise ValueError("工具名称为空")

    normalized = {
        "id": call_id,
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(arguments, ensure_ascii=False),
        },
    }
    return normalized, name, arguments


class ReActAgent:
    """让 LLM 自主决定工具调用与结束时机的循环引擎。"""

    def __init__(
        self,
        provider_factory: Any,
        tool_registry: Optional[ToolRegistry] = None,
        max_iterations: int = 6,
    ) -> None:
        if provider_factory is None:
            from src.core.providers.factory import ProviderFactory

            provider_factory = ProviderFactory()
        self.provider_factory = provider_factory
        self.tool_registry = tool_registry or get_registry()
        self.max_iterations = max(1, max_iterations)

    def _system_prompt(self, custom_prompt: Optional[str], context: Optional[Dict[str, Any]]) -> str:
        tools_description = "\n".join(
            f"- {registered_tool.name}: {registered_tool.description}"
            for registered_tool in self.tool_registry.get_all()
        ) or "无"
        prompt = custom_prompt or SYSTEM_PROMPT_TEMPLATE.format(tools_description=tools_description)
        if context:
            context_text = json.dumps(context, ensure_ascii=False, default=str)
            prompt = f"{prompt}\n当前请求上下文：{context_text}"
        return prompt

    @staticmethod
    def _result(
        answer: str,
        steps: List[ReActStep],
        started_at: float,
        total_tokens: int,
    ) -> ReActResult:
        return ReActResult(
            answer=answer,
            steps=steps,
            total_duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
            total_tokens=total_tokens,
        )

    async def run(
        self,
        question: str,
        system_prompt: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> ReActResult:
        """执行逐轮 Tool Calling，直到模型给出最终答案。"""
        started_at = time.perf_counter()
        steps: List[ReActStep] = []
        total_tokens = 0
        provider = self.provider_factory.get_provider()
        if provider is None:
            return self._result("AI 服务未配置", steps, started_at, total_tokens)

        tools = self.tool_registry.to_openai_tools()
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt(system_prompt, context)},
            {"role": "user", "content": question},
        ]
        last_content = ""

        for iteration in range(self.max_iterations):
            try:
                response = await provider.chat(
                    messages,
                    tools=tools if iteration < self.max_iterations - 1 else None,
                )
            except Exception as exc:
                logger.exception("LLM 调用失败: %s", exc)
                answer = steps[-1].observation if steps else "服务暂时不可用"
                return self._result(answer, steps, started_at, total_tokens)

            if not isinstance(response, dict):
                logger.error("LLM 返回了非对象响应: %s", type(response).__name__)
                answer = steps[-1].observation if steps else "服务暂时不可用"
                return self._result(answer, steps, started_at, total_tokens)

            last_content = str(response.get("content") or "")
            try:
                total_tokens += int(response.get("input_tokens") or 0)
                total_tokens += int(response.get("output_tokens") or 0)
            except (TypeError, ValueError):
                logger.warning("LLM 返回了无效 token 统计，已忽略")

            raw_tool_calls = response.get("tool_calls") or []
            if not isinstance(raw_tool_calls, list):
                logger.warning("LLM 返回了无效 tool_calls，已作为空列表处理")
                raw_tool_calls = []
            if not raw_tool_calls:
                return self._result(last_content, steps, started_at, total_tokens)

            normalized_calls: List[Dict[str, Any]] = []
            parsed_calls: List[tuple[str, str, Dict[str, Any], Optional[str]]] = []
            for call_index, raw_call in enumerate(raw_tool_calls):
                try:
                    normalized, name, arguments = _normalize_tool_call(
                        raw_call,
                        call_index,
                        call_id_prefix=f"call_{iteration}",
                    )
                    normalized_calls.append(normalized)
                    parsed_calls.append((normalized["id"], name, arguments, None))
                except ValueError as exc:
                    call_id = f"call_{iteration}_{call_index}"
                    name = "invalid_tool_call"
                    normalized_calls.append(
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {"name": name, "arguments": "{}"},
                        }
                    )
                    parsed_calls.append((call_id, name, {}, str(exc)))

            messages.append(
                {
                    "role": "assistant",
                    "content": last_content or None,
                    "tool_calls": normalized_calls,
                }
            )

            for call_id, name, arguments, parse_error in parsed_calls:
                tool_started_at = time.perf_counter()
                observation = ""
                if parse_error:
                    observation = f"工具调用解析失败: {parse_error}"
                else:
                    registered_tool = self.tool_registry.get(name)
                    if registered_tool is None:
                        observation = f"工具不存在: {name}"
                    else:
                        call_arguments = dict(arguments)
                        if name == "query_knowledge" and context:
                            # 身份作用域只能来自已认证请求，不能信任模型生成的参数。
                            call_arguments["tenant_id"] = context.get("tenant_id", "default_tenant")
                            call_arguments["department"] = context.get("department", "general")
                        try:
                            observation = str(await registered_tool.fn(**call_arguments))
                        except Exception as exc:
                            logger.warning("工具 %s 调用失败: %s", name, exc)
                            observation = f"工具调用失败: {type(exc).__name__}: {exc}"

                duration_ms = round((time.perf_counter() - tool_started_at) * 1000, 2)
                steps.append(
                    ReActStep(
                        thought=last_content,
                        action=name,
                        action_input=arguments,
                        observation=observation,
                        duration_ms=duration_ms,
                    )
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": name,
                        "content": observation,
                    }
                )

        fallback_answer = last_content or (steps[-1].observation if steps else "服务暂时不可用")
        return self._result(fallback_answer, steps, started_at, total_tokens)


class AgentRuntime:
    """保持原有接口不变，内部调用 ReActAgent。"""

    def __init__(
        self,
        provider_factory: Any = None,
        rag_pipeline_fn: Any = None,
        max_iterations: int = 4,
        timeout_seconds: float = 60.0,
    ) -> None:
        self.max_iterations = max_iterations
        self.timeout_seconds = timeout_seconds
        self._rag_pipeline_fn = rag_pipeline_fn
        self._react_agent = ReActAgent(
            provider_factory=provider_factory,
            max_iterations=max_iterations,
        )

    async def execute_graph(self, state: AgentState) -> AgentState:
        """执行 ReAct Agent，并转换为旧版 AgentState 结构。"""
        state.max_iterations = self.max_iterations
        department = getattr(state.request.department, "value", state.request.department)
        try:
            result = await asyncio.wait_for(
                self._react_agent.run(
                    question=state.request.question,
                    context={
                        "tenant_id": state.request.tenant_id,
                        "department": department,
                    },
                ),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning("Agent 执行超时: %.1fs", self.timeout_seconds)
            result = ReActResult(answer="服务暂时不可用")

        state.final_answer = result.answer
        state.next_node = "END"
        state.iteration = len(result.steps)
        state.steps = [
            {
                "iteration": index,
                "node": "react_agent",
                "thought": step.thought,
                "action": step.action,
                "action_input": step.action_input,
                "observation": step.observation,
                "execution_ms": step.duration_ms,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            for index, step in enumerate(result.steps, start=1)
        ]
        knowledge_steps = [step.observation for step in result.steps if step.action == "query_knowledge"]
        if knowledge_steps:
            state.rag_context = knowledge_steps[-1]
        logger.info(
            "ReAct execution trace | latency=%.1fms | iterations=%d | tokens=%d | answer_len=%d",
            result.total_duration_ms,
            state.iteration,
            result.total_tokens,
            len(state.final_answer),
        )
        return state
