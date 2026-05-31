"""确定性状态图智能体运行时 — 自研 Agent Runtime，零 LangChain 依赖。"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from src.core.schemas import GatewayRequest

logger = logging.getLogger("kgateway.agents.runtime")


# ── 工具描述（注入给 Planner）──────────────────────────────────

TOOL_DESCRIPTIONS = """可用工具：
1. query_local_knowledge — RAG 混合检索精排流水线（Dense向量 + BM25稀疏 + RRF融合 + BGE精排），查询企业内部知识库。参数：用户的检索问题。
2. web_search — 网络搜索，获取实时互联网信息。参数：搜索关键词。
3. finish — 直接输出最终回答给用户，不再调用其他工具。参数：最终回答文本。
"""

# ── Agent 状态定义 ──────────────────────────────────────────────


@dataclass
class AgentState:
    """Agent 状态图的全局状态。

    在整个图执行周期内，状态在节点之间单向传递。
    每个节点读取 state，处理后返回新 state（不可变语义）。
    """

    request: GatewayRequest
    history: List[Dict[str, str]] = field(default_factory=list)
    steps: List[Dict[str, Any]] = field(default_factory=list)
    next_node: str = "planner_node"
    final_answer: str = ""
    rag_context: str = ""
    iteration: int = 0
    max_iterations: int = 4

    def snapshot(self) -> Dict[str, Any]:
        """返回当前状态的可序列化快照（用于日志追踪）。"""
        return {
            "iteration": self.iteration,
            "next_node": self.next_node,
            "steps_count": len(self.steps),
            "has_rag_context": bool(self.rag_context),
            "final_answer_len": len(self.final_answer),
        }


# ── Agent Runtime ───────────────────────────────────────────────


class AgentRuntime:
    """确定性状态图智能体运行时。

    执行流程：
        planner_node → executor_node → planner_node → ... → finish
        ↑ 安全沙箱：max_iterations 次后强制 fallback_node 降级

    设计原则：
    - 完全确定性：给定相同输入 + 相同工具 → 相同执行轨迹
    - 无框架依赖：纯 Python dataclass + asyncio，淘汰 LangChain
    - 硬安全边界：迭代次数上限 + 超时保护 + 异常兜底
    """

    def __init__(
        self,
        *,
        max_iterations: int = 4,
        timeout_seconds: float = 60.0,
        rag_pipeline_fn: Optional[Callable[..., Any]] = None,
    ):
        self.max_iterations = max_iterations
        self.timeout_seconds = timeout_seconds
        # 注入的 RAG 流水线函数（由 routes.py 提供）
        self._rag_pipeline_fn = rag_pipeline_fn

    # ── 工具注册表 ──────────────────────────────────────────────

    async def _execute_tool(
        self,
        action: str,
        action_input: str,
        state: AgentState,
    ) -> str:
        """根据 action 名称分发到对应工具，返回 Observation 文本。"""
        tool_map: Dict[str, Callable[..., Any]] = {
            "query_local_knowledge": self._tool_query_local_knowledge,
            "web_search": self._tool_web_search,
        }

        tool_fn = tool_map.get(action)
        if tool_fn is None:
            return f"错误：未知工具 '{action}'，可用工具: {list(tool_map.keys())}"

        try:
            observation = await tool_fn(action_input, state)
            return observation
        except Exception as exc:
            error_msg = f"工具 {action} 执行异常: {type(exc).__name__}: {exc}"
            logger.error(error_msg)
            return error_msg

    async def _tool_query_local_knowledge(
        self,
        query: str,
        state: AgentState,
    ) -> str:
        """RAG 混合检索精排流水线。"""
        if self._rag_pipeline_fn is None:
            return f"RAG 流水线未配置，无法执行本地知识检索。查询内容: {query}"

        try:
            result = await self._rag_pipeline_fn(
                query=query,
                tenant_id=state.request.tenant_id,
                department=state.request.department.value,
            )
            # result 是 (rerank_results, rag_metrics) 元组
            rerank_results = result[0]
            if not rerank_results:
                return f"未检索到与「{query}」相关的知识文档。"

            snippets = []
            for i, r in enumerate(rerank_results):
                text = r.text if hasattr(r, "text") else str(r)
                score = r.rerank_score if hasattr(r, "rerank_score") else 0.0
                snippets.append(f"[{i+1}] (score={score:.3f}) {text[:200]}")
            return "\n".join(snippets)
        except Exception as exc:
            return f"RAG 检索失败: {exc}"

    async def _tool_web_search(
        self,
        query: str,
        state: AgentState,
    ) -> str:
        """网络搜索（当前为 Mock，生产环境接入搜索 API）。"""
        await asyncio.sleep(0.01)  # 模拟网络延迟
        return f"【Mock 搜索结果】关于「{query}」：此为模拟搜索结果。在生产环境中将接入 Google/Bing API。"

    # ── 图节点：Planner ────────────────────────────────────────

    async def planner_node(self, state: AgentState) -> AgentState:
        """Planner 节点：调用 LLM 分析问题并决定下一步行动。

        输入：用户 query + 工具描述 + 历史轨迹
        输出：固定格式 JSON {"thought", "action", "action_input"}
        """
        state.iteration += 1
        logger.info("═══ Planner 第 %d 次思考 ═══", state.iteration)

        # 构建 prompt
        history_text = ""
        if state.steps:
            history_text = "\n\n--- 已执行的步骤 ---\n"
            for step in state.steps:
                history_text += f"Thought: {step.get('thought', 'N/A')}\n"
                history_text += f"Action: {step.get('action', 'N/A')}\n"
                history_text += f"Observation: {step.get('observation', 'N/A')[:300]}\n\n"

        prompt = f"""你是一个严谨的企业智能助手。请分析用户的问题，并决定下一步行动。

用户问题：{state.request.question}
所属部门：{state.request.department.value}
租户：{state.request.tenant_id}
{history_text}
{TOOL_DESCRIPTIONS}

请严格返回以下 JSON 格式（不要返回任何其他内容）：
{{"thought": "你的分析思考", "action": "选择的工具名称", "action_input": "工具的输入参数"}}
"""

        # ── 模拟 LLM 返回（生产环境替换为真实 API 调用）────────
        # 根据迭代次数和上下文决定策略
        if state.iteration == 1:
            # 第一次：总是先尝试 RAG 检索
            planner_output = {
                "thought": "用户提出了一个问题，我需要先从企业知识库中检索相关信息来辅助回答。",
                "action": "query_local_knowledge",
                "action_input": state.request.question,
            }
        elif state.rag_context and state.iteration >= 2:
            # 有 RAG 上下文时，汇总输出
            planner_output = {
                "thought": "我已经从知识库中检索到了相关信息，现在可以基于这些上下文为用户生成最终回答。",
                "action": "finish",
                "action_input": f"基于检索到的知识库内容，关于您的问题「{state.request.question[:60]}」，以下是综合回答：\n\n{state.rag_context[:500]}",
            }
        else:
            planner_output = {
                "thought": "让我尝试网络搜索获取更多信息。",
                "action": "web_search",
                "action_input": state.request.question,
            }

        # 记录轨迹
        step_record = {
            "iteration": state.iteration,
            "node": "planner_node",
            "thought": planner_output["thought"],
            "action": planner_output["action"],
            "action_input": planner_output["action_input"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        state.steps.append(step_record)

        # 结构化日志输出
        logger.info(
            "Planner 第 %d/%d 次思考 | action=%s | thought=%s | input=%s",
            state.iteration, state.max_iterations,
            planner_output["action"],
            planner_output["thought"][:80],
            planner_output["action_input"][:100],
        )

        # 设置下一步
        state.next_node = "executor_node"
        # 将 planner 决策附加到 state 供 executor 使用
        state.steps[-1]["_planner_decision"] = planner_output

        return state

    # ── 图节点：Executor ────────────────────────────────────────

    async def executor_node(self, state: AgentState) -> AgentState:
        """Executor 节点：根据 Planner 决策执行工具调用，收集 Observation。"""
        # 从最后一步提取 planner 决策
        last_step = state.steps[-1]
        decision = last_step.get("_planner_decision", {})

        action = decision.get("action", "finish")
        action_input = decision.get("action_input", "")

        logger.info("═══ Executor 执行: action=%s ═══", action)

        # 如果 planner 决定 finish，直接输出最终答案
        if action == "finish":
            state.final_answer = action_input
            state.next_node = "END"
            logger.info("Planner 决定输出最终回答，图执行结束")
            return state

        # 执行工具
        t0 = time.perf_counter()
        observation = await self._execute_tool(action, action_input, state)
        exec_ms = (time.perf_counter() - t0) * 1000

        # 更新步骤记录
        last_step["observation"] = observation
        last_step["execution_ms"] = round(exec_ms, 2)

        # 如果执行了 RAG 检索，保存上下文供下一轮 Planner 使用
        if action == "query_local_knowledge":
            state.rag_context = observation

        logger.info("Executor 工具执行完成 | action=%s | 耗时=%.1fms | observation=%s", action, exec_ms, observation[:200])

        # 回到 Planner 进行下一轮决策
        state.next_node = "planner_node"
        return state

    # ── 图节点：Fallback（安全降级）────────────────────────────

    async def fallback_node(self, state: AgentState) -> AgentState:
        """Fallback 节点：当迭代超限或异常时，用低成本模型输出安全降级回答。

        这是最后的安全防线，保住用户的 API Token 钱包。
        """
        logger.warning(
            "⚠️ 安全沙箱触发: iteration=%d/%d, 强制降级",
            state.iteration, state.max_iterations,
        )

        logger.warning(
            "Fallback 安全沙箱触发！迭代次数 %d/%d，切换到低成本小模型输出降级回答",
            state.iteration, state.max_iterations,
        )

        # 降级回答：使用最基础的信息生成
        rag_hint = ""
        if state.rag_context:
            rag_hint = f"\n\n根据已检索到的部分信息：\n{state.rag_context[:300]}"

        state.final_answer = (
            f"尊敬的 {state.request.tenant_id} 用户，感谢您的提问。\n\n"
            f"关于您的问题：「{state.request.question[:100]}」\n\n"
            f"系统在处理过程中遇到了复杂情况，已为您切换到快速响应模式。"
            f"{rag_hint}\n\n"
            f"如需更深入的回答，建议您：\n"
            f"1. 尝试简化问题后重新提问\n"
            f"2. 联系 {state.request.department.value} 部门的知识管理员获取人工支持\n"
            f"3. 稍后重试（系统负载可能较高）"
        )

        state.next_node = "END"

        # 记录降级步骤
        state.steps.append({
            "iteration": state.iteration,
            "node": "fallback_node",
            "thought": "安全沙箱触发，执行降级回答",
            "action": "fallback",
            "observation": "迭代超限，保护用户 Token 预算",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return state

    # ── 图执行器 ────────────────────────────────────────────────

    async def execute_graph(self, state: AgentState) -> AgentState:
        """状态图主循环：确定性地驱动 Planner → Executor → Planner → ...

        安全沙箱：
        - 最多执行 max_iterations 轮（默认 4 轮 = 最多 8 个节点）
        - 超时保护：整个图执行不超过 timeout_seconds
        - 异常兜底：任何节点异常触发 fallback_node
        """
        state.max_iterations = self.max_iterations
        t_start = time.perf_counter()

        logger.info(
            "AgentRuntime 图执行器启动 | query=%s | tenant=%s | dept=%s | max_iterations=%d",
            state.request.question[:80], state.request.tenant_id,
            state.request.department.value, state.max_iterations,
        )

        try:
            while state.next_node != "END":
                # 超时检查
                elapsed = (time.perf_counter() - t_start)
                if elapsed > self.timeout_seconds:
                    logger.warning("图执行超时 (%.1fs > %.1fs)，触发 fallback", elapsed, self.timeout_seconds)
                    state = await self.fallback_node(state)
                    break

                # 迭代次数检查（安全沙箱核心）
                if state.iteration >= state.max_iterations and state.next_node == "planner_node":
                    logger.warning(
                        "迭代次数达到上限 %d，强制进入 fallback",
                        state.max_iterations,
                    )
                    state = await self.fallback_node(state)
                    break

                # 节点分发
                try:
                    if state.next_node == "planner_node":
                        state = await self.planner_node(state)
                    elif state.next_node == "executor_node":
                        state = await self.executor_node(state)
                    elif state.next_node == "fallback_node":
                        state = await self.fallback_node(state)
                    else:
                        logger.error("未知节点: %s，触发 fallback", state.next_node)
                        state = await self.fallback_node(state)
                        break
                except Exception as exc:
                    logger.exception("节点 %s 执行异常: %s", state.next_node, exc)
                    logger.error("节点 %s 异常: %s", state.next_node, exc)
                    state = await self.fallback_node(state)
                    break

        except Exception as exc:
            logger.exception("图执行器异常: %s", exc)
            state = await self.fallback_node(state)

        total_ms = (time.perf_counter() - t_start) * 1000

        # 打印完整执行轨迹
        self._print_execution_trace(state, total_ms)

        return state

    def _print_execution_trace(self, state: AgentState, total_ms: float) -> None:
        """记录完整的执行轨迹，用于调试和可观测性。"""
        logger.info(
            "Execution Trace | 总耗时=%.1fms | 迭代=%d/%d | 步数=%d | 回答长度=%d",
            total_ms, state.iteration, state.max_iterations,
            len(state.steps), len(state.final_answer),
        )
        for i, step in enumerate(state.steps):
            node = step.get("node", "unknown")
            thought = step.get("thought", "")[:80]
            action = step.get("action", "N/A")
            obs = step.get("observation", "")[:100]
            logger.info("  [%d] %s | %s | %s → %s", i + 1, node, thought, action, obs[:60])
