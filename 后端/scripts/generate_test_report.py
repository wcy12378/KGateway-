"""运行全项目验证并生成 docs/reports/test_report.md。"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "后端"
FRONTEND_DIR = PROJECT_ROOT / "前端"
REPORT_PATH = PROJECT_ROOT / "docs" / "reports" / "test_report.md"
ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


@dataclass(frozen=True)
class CommandResult:
    command: tuple[str, ...]
    returncode: int
    output: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def run_command(command: list[str], cwd: Path) -> CommandResult:
    """执行命令并合并 stdout/stderr，确保后续报告步骤仍可继续。"""
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        return CommandResult(tuple(command), completed.returncode, completed.stdout)
    except OSError as exc:
        return CommandResult(tuple(command), 127, f"{type(exc).__name__}: {exc}")


def parse_pytest_report(path: Path) -> tuple[dict[str, float | int], Counter[str], Counter[str]]:
    """从 pytest JUnit XML 提取统计、分类和跳过原因。"""
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    testcases = [case for suite in suites for case in suite.findall("testcase")]
    failures = sum(case.find("failure") is not None for case in testcases)
    errors = sum(case.find("error") is not None for case in testcases)
    skipped = sum(case.find("skipped") is not None for case in testcases)
    total = len(testcases)
    duration = sum(float(suite.attrib.get("time", 0) or 0) for suite in suites)

    categories: Counter[str] = Counter()
    skip_reasons: Counter[str] = Counter()
    for case in testcases:
        node = f"{case.attrib.get('classname', '')}::{case.attrib.get('name', '')}".lower()
        categories[classify_test(node)] += 1
        skipped_element = case.find("skipped")
        if skipped_element is not None:
            reason = skipped_element.attrib.get("message") or (skipped_element.text or "").strip()
            skip_reasons[reason or "未提供原因"] += 1

    stats: dict[str, float | int] = {
        "total": total,
        "passed": total - failures - errors - skipped,
        "failed": failures,
        "errors": errors,
        "skipped": skipped,
        "duration": duration,
    }
    return stats, categories, skip_reasons


def classify_test(node: str) -> str:
    """按有序规则把每个后端测试唯一归入一个覆盖分类。"""
    rules = (
        ("E2E", ("test_e2e_llm",)),
        ("记忆", ("test_agent_memory", "memory_")),
        ("工作流", ("test_agent_workflow", "workflow_")),
        ("SSE 协议", ("test_stream_contract", "heartbeat", "streaming_tasks")),
        ("安全", ("test_phase1_security", "jwt", "api_key", "audit_", "identity")),
        ("路由", ("test_provider_routing", "router_")),
        ("Provider", ("provider_", "deepseek", "openai", "gemini", "fallback")),
        ("存储", ("test_storage", "qdrant", "bm25", "neo4j", "semantic_cache")),
        ("编排", ("test_orchestrator", "test_fast_lane", "rag_", "circuit_breaker", "cache_")),
        ("Agent", ("test_react_agent", "agent_", "tool_", "prompt_", "calculator")),
    )
    for category, markers in rules:
        if any(marker in node for marker in markers):
            return category
    return "其他"


def parse_vitest_report(path: Path) -> dict[str, float | int]:
    """从 Vitest JSON reporter 输出提取稳定统计。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    results = data.get("testResults") or []
    end_time = max((float(item.get("endTime") or 0) for item in results), default=0)
    start_time = float(data.get("startTime") or 0)
    duration = max(0.0, (end_time - start_time) / 1000) if end_time else 0.0
    return {
        "files": len(results),
        "total": int(data.get("numTotalTests") or 0),
        "passed": int(data.get("numPassedTests") or 0),
        "failed": int(data.get("numFailedTests") or 0),
        "skipped": int(data.get("numPendingTests") or 0),
        "duration": duration,
    }


def clean_output(output: str) -> str:
    return ANSI_RE.sub("", output).replace("\r", "")


def output_tail(output: str, lines: int = 5) -> str:
    non_empty = [line.strip() for line in clean_output(output).splitlines() if line.strip()]
    return "\n".join(non_empty[-lines:]) or "（无输出）"


def status_text(result: CommandResult) -> str:
    return "通过" if result.ok else f"失败（退出码 {result.returncode}）"


def render_report(
    pytest_result: CommandResult,
    pytest_stats: dict[str, float | int] | None,
    categories: Counter[str],
    skip_reasons: Counter[str],
    vitest_result: CommandResult,
    vitest_stats: dict[str, float | int] | None,
    build_result: CommandResult,
    parse_errors: list[str],
) -> str:
    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    lines = [
        "# KAgent 测试报告",
        "",
        f"> 生成时间：{generated_at}",
        f"> 运行环境：Python {platform.python_version()} / {platform.system()} {platform.release()}",
        f"> DeepSeek E2E：{'已启用' if os.getenv('KAGENT_DEEPSEEK_API_KEY') else '未配置 Key，自动跳过'}",
        f"> DeepSeek 模型：{os.getenv('KAGENT_DEEPSEEK_MODEL', 'deepseek-chat')}",
        "",
        "## 后端测试概览",
        "",
        f"执行状态：**{status_text(pytest_result)}**",
        "",
        "| 指标 | 数值 |",
        "|------|:----:|",
    ]
    if pytest_stats is None:
        lines.append("| 解析状态 | 无法读取 JUnit XML |")
    else:
        lines.extend(
            [
                f"| 总测试数 | {pytest_stats['total']} |",
                f"| 通过 | {pytest_stats['passed']} |",
                f"| 失败 | {pytest_stats['failed']} |",
                f"| 错误 | {pytest_stats['errors']} |",
                f"| 跳过 | {pytest_stats['skipped']} |",
                f"| 耗时 | {float(pytest_stats['duration']):.2f}s |",
            ]
        )

    descriptions = {
        "Provider": "工厂隔离、模型适配、fallback 与连接复用",
        "Agent": "ReAct 工具调用、异常恢复、迭代上限",
        "编排": "熔断降级、缓存路径、RAG 与快速路径",
        "SSE 协议": "帧格式、协议版本、心跳与流任务",
        "安全": "JWT、API Key、限流、身份与审计",
        "记忆": "记忆存储、检索、隔离与降级",
        "路由": "Provider 路由、健康状态与恢复",
        "工作流": "顺序、规则路由、并行与合成",
        "存储": "Qdrant、BM25、Neo4j 与语义缓存",
        "E2E": "真实 DeepSeek Tool Calling",
        "其他": "配置、通用契约及未归入上述模块的测试",
    }
    category_order = ("Provider", "Agent", "编排", "SSE 协议", "安全", "记忆", "路由", "工作流", "存储", "E2E", "其他")
    lines.extend(
        [
            "",
            "## 后端测试覆盖分类",
            "",
            "| 模块 | 测试数 | 覆盖内容 |",
            "|:----|:-----:|---------|",
        ]
    )
    for category in category_order:
        lines.append(f"| {category} | {categories.get(category, 0)} | {descriptions[category]} |")

    lines.extend(["", "### 跳过项", ""])
    if skip_reasons:
        for reason, count in skip_reasons.most_common():
            lines.append(f"- {count} 项：{reason}")
    else:
        lines.append("- 无")

    lines.extend(
        [
            "",
            "## 前端测试",
            "",
            f"执行状态：**{status_text(vitest_result)}**",
            "",
            "| 指标 | 数值 |",
            "|------|:----:|",
        ]
    )
    if vitest_stats is None:
        lines.append("| 解析状态 | 无法读取 Vitest JSON |")
    else:
        lines.extend(
            [
                f"| 测试文件 | {vitest_stats['files']} |",
                f"| 总测试数 | {vitest_stats['total']} |",
                f"| 通过 | {vitest_stats['passed']} |",
                f"| 失败 | {vitest_stats['failed']} |",
                f"| 跳过 | {vitest_stats['skipped']} |",
                f"| 耗时 | {float(vitest_stats['duration']):.2f}s |",
            ]
        )

    lines.extend(
        [
            "",
            "## 前端构建",
            "",
            f"执行状态：**{status_text(build_result)}**",
            "",
            "```text",
            output_tail(build_result.output),
            "```",
        ]
    )
    if parse_errors:
        lines.extend(["", "## 报告解析异常", ""])
        lines.extend(f"- {error}" for error in parse_errors)
    lines.extend(
        [
            "",
            "## 复现命令",
            "",
            "```powershell",
            "cd 后端",
            "python scripts/generate_test_report.py",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    npm = shutil.which("npm") or "npm"
    npx = shutil.which("npx") or "npx"
    parse_errors: list[str] = []
    categories: Counter[str] = Counter()
    skip_reasons: Counter[str] = Counter()
    pytest_stats: dict[str, float | int] | None = None
    vitest_stats: dict[str, float | int] | None = None

    with tempfile.TemporaryDirectory(prefix="kagent-test-report-") as temp_dir:
        temp_path = Path(temp_dir)
        junit_path = temp_path / "pytest.xml"
        vitest_path = temp_path / "vitest.json"

        pytest_result = run_command(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/",
                "-p",
                "no:cacheprovider",
                "-v",
                "--tb=short",
                "--no-header",
                f"--junitxml={junit_path}",
            ],
            BACKEND_DIR,
        )
        if junit_path.exists():
            try:
                pytest_stats, categories, skip_reasons = parse_pytest_report(junit_path)
            except (ET.ParseError, OSError, ValueError) as exc:
                parse_errors.append(f"pytest JUnit 解析失败：{type(exc).__name__}: {exc}")
        else:
            parse_errors.append("pytest 未生成 JUnit XML")

        vitest_result = run_command(
            [npx, "vitest", "run", "--reporter=json", f"--outputFile={vitest_path}"],
            FRONTEND_DIR,
        )
        if vitest_path.exists():
            try:
                vitest_stats = parse_vitest_report(vitest_path)
            except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
                parse_errors.append(f"Vitest JSON 解析失败：{type(exc).__name__}: {exc}")
        else:
            parse_errors.append("Vitest 未生成 JSON 报告")

        build_result = run_command([npm, "run", "build"], FRONTEND_DIR)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        render_report(
            pytest_result,
            pytest_stats,
            categories,
            skip_reasons,
            vitest_result,
            vitest_stats,
            build_result,
            parse_errors,
        ),
        encoding="utf-8",
    )
    print(f"测试报告已生成：{REPORT_PATH}")

    all_ok = pytest_result.ok and vitest_result.ok and build_result.ok and not parse_errors
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
