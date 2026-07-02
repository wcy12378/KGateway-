"""LLM 驱动的 ReAct Tool Calling Agent。"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.core.agent.memory import MemoryManager
from src.core.audit import AuditEntry, AuditLogger
from src.core.prompts.registry import PromptNotFoundError, PromptRegistry, get_registry as get_prompt_registry
from src.core.schemas import GatewayRequest
from src.core.tools.registry import TRUSTED_CONTEXT_PARAMETERS, ToolRegistry, get_registry

logger = logging.getLogger("kagent.core.agent.react_agent")

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
    status: str = "completed"
    error: Optional[str] = None
    provider_used: str = ""
    model_used: str = ""


@dataclass
class AgentState:
    """保持现有编排层兼容的 Agent 执行状态。"""

    request: GatewayRequest
    history: List[Dict[str, str]] = field(default_factory=list)
    steps: List[Dict[str, Any]] = field(default_factory=list)
    next_node: str = "planner_node"
    final_answer: str = ""
    rag_context: str = ""
    trace_id: str = ""
    iteration: int = 0
    max_iterations: int = 4
    provider_used: str = ""
    model_used: str = ""

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
        memory_manager: Optional[MemoryManager] = None,
        default_system_prompt: Optional[str] = None,
        prompt_registry: Optional[PromptRegistry] = None,
        prompt_name: str = "react_default",
        prompt_version: Optional[str] = None,
        audit_logger: Optional[AuditLogger] = None,
    ) -> None:
        if provider_factory is None:
            from src.core.providers.factory import ProviderFactory

            provider_factory = ProviderFactory()
        self.provider_factory = provider_factory
        self.tool_registry = tool_registry or get_registry()
        self.max_iterations = max(1, max_iterations)
        self.memory_manager = memory_manager
        self.default_system_prompt = default_system_prompt
        self.prompt_registry = prompt_registry or get_prompt_registry()
        self.prompt_name = prompt_name
        self.prompt_version = prompt_version
        self.audit_logger = audit_logger

    def _system_prompt(self, custom_prompt: Optional[str], context: Optional[Dict[str, Any]]) -> str:
        tools_description = "\n".join(
            f"- {registered_tool.name}: {registered_tool.description}"
            for registered_tool in self.tool_registry.get_all()
        ) or "无"
        if custom_prompt or self.default_system_prompt:
            prompt = custom_prompt or self.default_system_prompt or ""
            if context:
                context_text = json.dumps(context, ensure_ascii=False, default=str)
                prompt = f"{prompt}\n当前请求上下文：{context_text}"
            return prompt

        context_text = json.dumps(context or {}, ensure_ascii=False, default=str)
        try:
            return self.prompt_registry.render(
                self.prompt_name,
                self.prompt_version,
                tools_description=tools_description,
                request_context=context_text,
            )
        except PromptNotFoundError:
            if self.prompt_name == "react_default":
                raise
            logger.warning(
                "Prompt '%s' v%s 未注册，回退 react_default 活动版本",
                self.prompt_name,
                self.prompt_version or "active",
            )
            return self.prompt_registry.render(
                "react_default",
                tools_description=tools_description,
                request_context=context_text,
            )

    @staticmethod
    def _result(
        answer: str,
        steps: List[ReActStep],
        started_at: float,
        total_tokens: int,
        *,
        status: str = "completed",
        error: Optional[str] = None,
        provider_used: str = "",
        model_used: str = "",
    ) -> ReActResult:
        return ReActResult(
            answer=answer,
            steps=steps,
            total_duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
            total_tokens=total_tokens,
            status=status,
            error=error,
            provider_used=provider_used,
            model_used=model_used,
        )

    async def _memory_prompt(
        self,
        question: str,
        context: Optional[Dict[str, Any]],
    ) -> str:
        if self.memory_manager is None or not context:
            return ""
        user_id = str(context.get("user_id") or "")
        tenant_id = str(context.get("tenant_id") or "")
        if not user_id or not tenant_id:
            return ""
        try:
            memories = await self.memory_manager.get_relevant_memories(
                query=question,
                user_id=user_id,
                tenant_id=tenant_id,
            )
            return self.memory_manager.format_memories_for_prompt(memories)
        except Exception as exc:
            logger.warning("记忆检索失败，已跳过: %s", exc)
            return ""

    async def _finalize_result(
        self,
        answer: str,
        steps: List[ReActStep],
        started_at: float,
        total_tokens: int,
        *,
        question: str,
        context: Optional[Dict[str, Any]],
        persist_memory: bool,
        status: str = "completed",
        error: Optional[str] = None,
        provider_used: str = "",
        model_used: str = "",
    ) -> ReActResult:
        result = self._result(
            answer,
            steps,
            started_at,
            total_tokens,
            status=status,
            error=error,
            provider_used=provider_used,
            model_used=model_used,
        )
        if status != "completed" or not persist_memory or self.memory_manager is None or not context:
            return result
        try:
            await self.memory_manager.remember_exchange(
                question=question,
                answer=result.answer,
                user_id=str(context.get("user_id") or ""),
                tenant_id=str(context.get("tenant_id") or ""),
            )
        except Exception as exc:
            logger.warning("记忆存储失败，已跳过: %s", exc)
        return result

    async def _chat(self, messages: List[Dict[str, Any]], *, tools: Optional[list[dict]]) -> dict:
        """优先使用 Factory 的自动 fallback，兼容简单测试 Factory。"""
        fallback_chat = getattr(self.provider_factory, "chat_with_fallback", None)
        if callable(fallback_chat):
            return await fallback_chat(messages, tools=tools)
        provider = self.provider_factory.get_provider()
        if provider is None:
            raise RuntimeError("AI 服务未配置")
        response = await provider.chat(messages, tools=tools)
        if isinstance(response, dict):
            response.setdefault("provider", getattr(provider, "name", ""))
            models = provider.get_models() if hasattr(provider, "get_models") else []
            response.setdefault("model", models[0] if models else "")
        return response

    async def run(
        self,
        question: str,
        system_prompt: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        *,
        memory_query: Optional[str] = None,
        persist_memory: bool = True,
    ) -> ReActResult:
        """执行逐轮 Tool Calling，直到模型给出最终答案。"""
        started_at = time.perf_counter()
        steps: List[ReActStep] = []
        total_tokens = 0
        fallback_chat = getattr(self.provider_factory, "chat_with_fallback", None)
        if not callable(fallback_chat) and self.provider_factory.get_provider() is None:
            return await self._finalize_result(
                "AI 服务未配置",
                steps,
                started_at,
                total_tokens,
                question=question,
                context=context,
                persist_memory=persist_memory,
                status="failed",
                error="AI 服务未配置",
            )

        tools = self.tool_registry.to_openai_tools()
        prompt = self._system_prompt(system_prompt, context)
        memory_prompt = await self._memory_prompt(memory_query or question, context)
        if memory_prompt:
            prompt = f"{prompt}{memory_prompt}"
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": question},
        ]
        last_content = ""
        last_provider = ""
        last_model = ""

        for iteration in range(self.max_iterations):
            try:
                response = await self._chat(
                    messages,
                    tools=tools if iteration < self.max_iterations - 1 else None,
                )
            except Exception as exc:
                logger.exception("LLM 调用失败: %s", exc)
                answer = steps[-1].observation if steps else "服务暂时不可用"
                return await self._finalize_result(
                    answer,
                    steps,
                    started_at,
                    total_tokens,
                    question=question,
                    context=context,
                    persist_memory=persist_memory,
                    status="failed",
                    error=f"{type(exc).__name__}: {str(exc)[:300]}",
                )

            if not isinstance(response, dict):
                logger.error("LLM 返回了非对象响应: %s", type(response).__name__)
                answer = steps[-1].observation if steps else "服务暂时不可用"
                return await self._finalize_result(
                    answer,
                    steps,
                    started_at,
                    total_tokens,
                    question=question,
                    context=context,
                    persist_memory=persist_memory,
                    status="failed",
                    error=f"无效响应类型: {type(response).__name__}",
                )

            last_content = str(response.get("content") or "")
            last_provider = str(response.get("provider") or last_provider)
            last_model = str(response.get("model") or last_model)
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
                if not last_content.strip():
                    return await self._finalize_result(
                        "服务暂时不可用",
                        steps,
                        started_at,
                        total_tokens,
                        question=question,
                        context=context,
                        persist_memory=False,
                        status="failed",
                        error="LLM 返回空答案",
                        provider_used=last_provider,
                        model_used=last_model,
                    )
                return await self._finalize_result(
                    last_content,
                    steps,
                    started_at,
                    total_tokens,
                    question=question,
                    context=context,
                    persist_memory=persist_memory,
                    provider_used=last_provider,
                    model_used=last_model,
                )

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
                audit_timestamp = datetime.now(timezone.utc).isoformat()
                observation = ""
                effective_arguments = dict(arguments)
                call_succeeded = False
                if parse_error:
                    observation = f"工具调用解析失败: {parse_error}"
                else:
                    registered_tool = self.tool_registry.get(name)
                    if registered_tool is None:
                        observation = f"工具不存在: {name}"
                    else:
                        call_arguments = dict(arguments)
                        try:
                            properties = registered_tool.spec.parameters.get("properties", {})
                            scoped_parameters = set(properties) & TRUSTED_CONTEXT_PARAMETERS
                            try:
                                scoped_parameters.update(
                                    set(inspect.signature(registered_tool.fn).parameters)
                                    & TRUSTED_CONTEXT_PARAMETERS
                                )
                            except (TypeError, ValueError):
                                pass
                            if name == "query_knowledge":
                                scoped_parameters.update({"tenant_id", "department"})
                            for parameter_name in TRUSTED_CONTEXT_PARAMETERS:
                                call_arguments.pop(parameter_name, None)
                                if parameter_name in scoped_parameters and context:
                                    trusted_value = context.get(parameter_name)
                                    if trusted_value is not None:
                                        call_arguments[parameter_name] = getattr(
                                            trusted_value,
                                            "value",
                                            trusted_value,
                                        )
                            call_arguments = registered_tool.validate_arguments(call_arguments)
                            effective_arguments = call_arguments
                            observation = str(await registered_tool.fn(**call_arguments))
                            call_succeeded = True
                        except Exception as exc:
                            logger.warning("工具 %s 调用失败: %s", name, exc)
                            observation = f"工具调用失败: {type(exc).__name__}: {exc}"

                duration_ms = round((time.perf_counter() - tool_started_at) * 1000, 2)
                if self.audit_logger is not None:
                    try:
                        audit_context = context or {}
                        self.audit_logger.record(
                            AuditEntry(
                                timestamp=audit_timestamp,
                                user_id=str(audit_context.get("user_id") or ""),
                                tenant_id=str(audit_context.get("tenant_id") or ""),
                                session_id=str(audit_context.get("session_id") or ""),
                                trace_id=str(audit_context.get("trace_id") or ""),
                                workflow_name=str(audit_context.get("workflow_name") or ""),
                                agent_name=str(audit_context.get("agent_name") or "react_agent"),
                                call_id=call_id,
                                tool_name=name,
                                tool_params=effective_arguments,
                                result_status="success" if call_succeeded else "failure",
                                result_summary=observation,
                                duration_ms=duration_ms,
                            )
                        )
                    except Exception as exc:
                        logger.warning("工具审计记录失败，已跳过: %s", exc)
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
        return await self._finalize_result(
            fallback_answer,
            steps,
            started_at,
            total_tokens,
            question=question,
            context=context,
            persist_memory=False,
            status="max_iterations_exceeded",
            error="ReAct 达到最大迭代次数",
            provider_used=last_provider,
            model_used=last_model,
        )


class AgentRuntime:
    """保持原有接口不变，内部调用 ReActAgent。"""

    def __init__(
        self,
        provider_factory: Any = None,
        rag_pipeline_fn: Any = None,
        max_iterations: int = 4,
        timeout_seconds: float = 60.0,
        memory_manager: Optional[MemoryManager] = None,
        prompt_registry: Optional[PromptRegistry] = None,
        audit_logger: Optional[AuditLogger] = None,
    ) -> None:
        self.max_iterations = max_iterations
        self.timeout_seconds = timeout_seconds
        self._rag_pipeline_fn = rag_pipeline_fn
        self._react_agent = ReActAgent(
            provider_factory=provider_factory,
            max_iterations=max_iterations,
            memory_manager=memory_manager,
            prompt_registry=prompt_registry,
            audit_logger=audit_logger,
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
                        "user_id": state.request.user_id,
                        "tenant_id": state.request.tenant_id,
                        "department": department,
                        "session_id": state.request.session_id,
                        "trace_id": state.trace_id,
                    },
                ),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning("Agent 执行超时: %.1fs", self.timeout_seconds)
            result = ReActResult(answer="服务暂时不可用", status="failed", error="执行超时")

        state.final_answer = result.answer
        state.provider_used = result.provider_used
        state.model_used = result.model_used
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
