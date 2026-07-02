"""Prompt 文件模板、版本和运行时激活状态管理。"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

logger = logging.getLogger("kagent.core.prompts.registry")

_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]{1,64}$")
_VERSION_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_VARIABLE_PATTERN = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


class PromptNotFoundError(KeyError):
    """模板或版本不存在。"""


class PromptRenderError(ValueError):
    """模板变量不完整。"""


@dataclass(frozen=True)
class PromptTemplate:
    """不可变、可校验的 Prompt 模板版本。"""

    name: str
    version: str
    template: str
    description: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    variables: tuple[str, ...] = field(init=False)
    content_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if not _NAME_PATTERN.fullmatch(self.name):
            raise ValueError(f"无效 Prompt 名称: {self.name!r}")
        if not _VERSION_PATTERN.fullmatch(self.version):
            raise ValueError(f"Prompt 版本必须是语义版本 x.y.z: {self.version!r}")
        if not self.template.strip():
            raise ValueError("Prompt 模板不能为空")

        variables = tuple(dict.fromkeys(_VARIABLE_PATTERN.findall(self.template)))
        residual = _VARIABLE_PATTERN.sub("", self.template)
        if "{" in residual or "}" in residual:
            raise ValueError("Prompt 仅支持 {variable} 形式的占位符")
        object.__setattr__(self, "variables", variables)
        object.__setattr__(
            self,
            "content_hash",
            hashlib.sha256(self.template.encode("utf-8")).hexdigest()[:12],
        )

    def render(self, **variables: Any) -> str:
        """严格渲染；缺少变量时拒绝生成不完整 Prompt。"""
        missing = [name for name in self.variables if name not in variables]
        if missing:
            raise PromptRenderError(
                f"Prompt '{self.name}' v{self.version} 缺少变量: {', '.join(missing)}"
            )
        return _VARIABLE_PATTERN.sub(
            lambda match: str(variables[match.group(1)]),
            self.template,
        )


class PromptRegistry:
    """线程安全的 Prompt 版本注册与激活中心。"""

    def __init__(self) -> None:
        self._versions: Dict[str, Dict[str, PromptTemplate]] = {}
        self._active_versions: Dict[str, str] = {}
        self._lock = threading.RLock()

    def register(self, template: PromptTemplate, *, activate: bool = False) -> None:
        """注册新版本；禁止同版本内容被静默覆盖。"""
        with self._lock:
            versions = self._versions.setdefault(template.name, {})
            existing = versions.get(template.version)
            if existing is not None and existing.content_hash != template.content_hash:
                raise ValueError(
                    f"Prompt '{template.name}' v{template.version} 已存在不同内容"
                )
            versions[template.version] = template
            if activate or template.name not in self._active_versions:
                self._active_versions[template.name] = template.version
        logger.info(
            "Prompt 已注册: %s v%s hash=%s",
            template.name,
            template.version,
            template.content_hash,
        )

    def activate(self, name: str, version: str) -> PromptTemplate:
        """原子切换指定模板的活动版本。"""
        with self._lock:
            template = self._versions.get(name, {}).get(version)
            if template is None:
                raise PromptNotFoundError(f"Prompt '{name}' v{version} 未注册")
            self._active_versions[name] = version
        logger.info("Prompt 活动版本已切换: %s -> v%s", name, version)
        return template

    def active_version(self, name: str) -> Optional[str]:
        with self._lock:
            return self._active_versions.get(name)

    def get(self, name: str, version: Optional[str] = None) -> Optional[PromptTemplate]:
        with self._lock:
            selected_version = version or self._active_versions.get(name)
            if selected_version is None:
                return None
            return self._versions.get(name, {}).get(selected_version)

    def render(
        self,
        name: str,
        version: Optional[str] = None,
        **variables: Any,
    ) -> str:
        template = self.get(name, version)
        if template is None:
            raise PromptNotFoundError(
                f"Prompt '{name}' v{version or 'active'} 未注册"
            )
        return template.render(**variables)

    def list(self) -> List[Dict[str, Any]]:
        """列出模板摘要，不暴露模板正文。"""
        with self._lock:
            return [
                {
                    "name": name,
                    "active_version": self._active_versions.get(name),
                    "versions": sorted(
                        versions,
                        key=lambda value: tuple(int(part) for part in value.split(".")),
                    ),
                    "description": versions[self._active_versions[name]].description,
                    "variables": list(versions[self._active_versions[name]].variables),
                    "hash": versions[self._active_versions[name]].content_hash,
                }
                for name, versions in sorted(self._versions.items())
                if name in self._active_versions
            ]

    def load_directory(self, directory: Path) -> int:
        """从受控 manifest 加载模板文件。"""
        root = directory.resolve()
        manifest_path = root / "manifest.json"
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        entries = raw.get("prompts")
        if not isinstance(entries, list):
            raise ValueError("Prompt manifest 缺少 prompts 列表")

        pending: list[tuple[PromptTemplate, bool]] = []
        for entry in entries:
            if not isinstance(entry, Mapping):
                raise ValueError("Prompt manifest 条目必须是对象")
            file_name = str(entry.get("file") or "")
            file_path = (root / file_name).resolve()
            try:
                file_path.relative_to(root)
            except ValueError as exc:
                raise ValueError(f"Prompt 文件越出模板目录: {file_name}") from exc
            template = PromptTemplate(
                name=str(entry.get("name") or ""),
                version=str(entry.get("version") or ""),
                template=file_path.read_text(encoding="utf-8").strip(),
                description=str(entry.get("description") or ""),
            )
            pending.append((template, bool(entry.get("active", False))))

        with self._lock:
            for template, _ in pending:
                existing = self._versions.get(template.name, {}).get(template.version)
                if existing is not None and existing.content_hash != template.content_hash:
                    raise ValueError(
                        f"Prompt '{template.name}' v{template.version} 已存在不同内容"
                    )
            for template, activate in pending:
                versions = self._versions.setdefault(template.name, {})
                versions[template.version] = template
                if activate or template.name not in self._active_versions:
                    self._active_versions[template.name] = template.version

        for template, _ in pending:
            logger.info(
                "Prompt 已加载: %s v%s hash=%s",
                template.name,
                template.version,
                template.content_hash,
            )
        return len(pending)


_registry = PromptRegistry()
_registry_loaded = False
_registry_lock = threading.Lock()


def get_registry() -> PromptRegistry:
    """返回已加载项目默认模板的进程级注册表。"""
    global _registry_loaded
    if not _registry_loaded:
        with _registry_lock:
            if not _registry_loaded:
                template_dir = Path(__file__).resolve().parent / "templates"
                _registry.load_directory(template_dir)
                _registry_loaded = True
    return _registry
