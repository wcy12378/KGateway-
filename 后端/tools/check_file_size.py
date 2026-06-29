"""源码文件行数治理检查脚本。

本脚本负责扫描项目业务源码，发现超过 300 行的预警文件和超过
500 行的强制拆分文件。它不修改源码，只输出检查结果并通过退出码
告诉调用方是否存在必须处理的超限文件。
"""

from __future__ import annotations

import argparse
from pathlib import Path

WARNING_LIMIT = 300
ERROR_LIMIT = 500
DEFAULT_INCLUDE_SUFFIXES = {".py", ".ts", ".tsx"}
DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}
DEFAULT_SCAN_ROOTS = ("src", "frontend/src")


def iter_source_files(project_root: Path, scan_roots: tuple[str, ...]) -> list[Path]:
    """返回需要纳入治理检查的源码文件列表。"""

    files: list[Path] = []
    for root_name in scan_roots:
        root = project_root / root_name
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in DEFAULT_INCLUDE_SUFFIXES:
                continue
            if any(part in DEFAULT_EXCLUDED_DIRS for part in path.parts):
                continue
            files.append(path)
    return sorted(files)


def count_lines(path: Path) -> int:
    """按物理行统计文件长度，空行和注释都计入。"""

    try:
        with path.open("r", encoding="utf-8") as handle:
            return sum(1 for _ in handle)
    except UnicodeDecodeError:
        with path.open("r", encoding="utf-8-sig") as handle:
            return sum(1 for _ in handle)


def build_report(project_root: Path, scan_roots: tuple[str, ...]) -> list[tuple[int, Path]]:
    """构建按行数倒序排列的超 300 行文件报告。"""

    report: list[tuple[int, Path]] = []
    for path in iter_source_files(project_root, scan_roots):
        lines = count_lines(path)
        if lines >= WARNING_LIMIT:
            report.append((lines, path.relative_to(project_root)))
    return sorted(report, reverse=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="检查业务源码文件行数是否超过治理阈值。")
    parser.add_argument(
        "--root",
        default=".",
        help="项目根目录，默认当前目录。",
    )
    parser.add_argument(
        "--scan-root",
        action="append",
        dest="scan_roots",
        help="需要扫描的源码根目录，可重复传入；默认扫描 src 和 frontend/src。",
    )
    args = parser.parse_args()

    project_root = Path(args.root).resolve()
    scan_roots = tuple(args.scan_roots or DEFAULT_SCAN_ROOTS)
    report = build_report(project_root, scan_roots)

    if not report:
        print("OK: 未发现 300 行以上业务源码文件。")
        return 0

    has_error = False
    print("文件行数治理检查结果：")
    for lines, relative_path in report:
        level = "ERROR" if lines >= ERROR_LIMIT else "WARN"
        has_error = has_error or level == "ERROR"
        print(f"{level}: {relative_path} ({lines} 行)")

    if has_error:
        print("存在 500 行以上文件，必须拆分或写明豁免理由。")
        return 1

    print("仅存在 300-499 行预警文件，需要提醒并给出拆分判断。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
