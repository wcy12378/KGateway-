"""工具调用审计记录、脱敏和内存查询。"""

from __future__ import annotations

import json
import logging
import re
import threading
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional

logger = logging.getLogger("kagent.core.audit")

_SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "credential",
    "credentials",
    "password",
    "passwd",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "private_key",
    "access_key",
}
_BEARER_PATTERN = re.compile(r"(?i)(bearer\s+)[a-z0-9._~+/=-]+")
_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)([\"']?(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|token)"
    r"[\"']?\s*[:=]\s*[\"']?)([^\"'\s,;}]+)"
)
_URI_CREDENTIAL_PATTERN = re.compile(
    r"(?i)([a-z][a-z0-9+.-]*://[^:/\s]+:)([^@/\s]+)(@)"
)
_JWT_PATTERN = re.compile(r"\beyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\b")
_COOKIE_PATTERN = re.compile(r"(?i)((?:set-)?cookie\s*:\s*)[^\r\n]+")
_MAX_DEPTH = 5
_MAX_ITEMS = 50
_MAX_VALUE_CHARS = 500
_MAX_RESULT_CHARS = 200


def _is_sensitive_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", key.casefold()).strip("_")
    compact = normalized.replace("_", "")
    return (
        normalized in _SENSITIVE_KEYS
        or compact in _SENSITIVE_KEYS
        or normalized.endswith(("_password", "_secret", "_token", "_key"))
    )


def _mask_value(value: Any) -> str:
    text = str(value)
    if len(text) <= 4:
        return "****"
    return f"{text[:2]}****{text[-2:]}"


def redact_value(value: Any, *, _depth: int = 0) -> Any:
    """递归脱敏并限制体积，确保审计记录可序列化。"""
    if _depth >= _MAX_DEPTH:
        return "<max-depth>"
    if isinstance(value, dict):
        result: Dict[str, Any] = {}
        for index, (raw_key, item) in enumerate(value.items()):
            if index >= _MAX_ITEMS:
                result["<truncated>"] = f"{len(value) - _MAX_ITEMS} more items"
                break
            key = str(raw_key)[:128]
            result[key] = (
                _mask_value(item)
                if _is_sensitive_key(key)
                else redact_value(item, _depth=_depth + 1)
            )
        return result
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        sanitized = [redact_value(item, _depth=_depth + 1) for item in items[:_MAX_ITEMS]]
        if len(items) > _MAX_ITEMS:
            sanitized.append(f"<truncated:{len(items) - _MAX_ITEMS}>")
        return sanitized
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return sanitize_text(str(value), max_chars=_MAX_VALUE_CHARS)


def sanitize_text(value: str, *, max_chars: int = _MAX_RESULT_CHARS) -> str:
    """清洗结果摘要中的常见凭据并截断。"""
    text = re.sub(r"[\r\n\t]+", " ", str(value))
    text = _BEARER_PATTERN.sub(r"\1****", text)
    text = _ASSIGNMENT_PATTERN.sub(r"\1****", text)
    text = _URI_CREDENTIAL_PATTERN.sub(r"\1****\3", text)
    text = _JWT_PATTERN.sub("<redacted-jwt>", text)
    text = _COOKIE_PATTERN.sub(r"\1****", text)
    return text[:max_chars]


@dataclass(frozen=True)
class AuditEntry:
    """一条工具调用审计事件。"""

    audit_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    user_id: str = ""
    tenant_id: str = ""
    session_id: str = ""
    trace_id: str = ""
    workflow_name: str = ""
    agent_name: str = ""
    call_id: str = ""
    tool_name: str = ""
    tool_params: Dict[str, Any] = field(default_factory=dict)
    result_status: str = "failure"
    result_summary: str = ""
    duration_ms: float = 0.0


class AuditLogger:
    """线程安全环形审计缓冲区。"""

    def __init__(self, max_entries: int = 1000) -> None:
        if not 1 <= int(max_entries) <= 100_000:
            raise ValueError("max_entries 必须在 1-100000 之间")
        self.max_entries = int(max_entries)
        self._entries: Deque[AuditEntry] = deque(maxlen=self.max_entries)
        self._lock = threading.RLock()

    def record(self, entry: AuditEntry) -> None:
        """安全记录事件；仅输出已脱敏的结构化日志。"""
        safe_entry = replace(
            entry,
            tool_params=redact_value(entry.tool_params),
            result_summary=sanitize_text(entry.result_summary),
            duration_ms=round(max(float(entry.duration_ms), 0.0), 2),
            result_status="success" if entry.result_status == "success" else "failure",
        )
        with self._lock:
            self._entries.append(safe_entry)
        logger.info(
            "tool_audit %s",
            json.dumps(asdict(safe_entry), ensure_ascii=False, default=str),
        )

    def query(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        result_status: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """按最新优先分页查询审计记录。"""
        safe_limit = max(1, min(int(limit), 200))
        safe_offset = max(0, int(offset))
        with self._lock:
            entries = list(reversed(self._entries))
        if tenant_id is not None:
            entries = [entry for entry in entries if entry.tenant_id == tenant_id]
        if user_id is not None:
            entries = [entry for entry in entries if entry.user_id == user_id]
        if tool_name is not None:
            entries = [entry for entry in entries if entry.tool_name == tool_name]
        if result_status is not None:
            entries = [entry for entry in entries if entry.result_status == result_status]
        if trace_id is not None:
            entries = [entry for entry in entries if entry.trace_id == trace_id]

        total = len(entries)
        page = entries[safe_offset : safe_offset + safe_limit]
        return {
            "total": total,
            "limit": safe_limit,
            "offset": safe_offset,
            "entries": [asdict(entry) for entry in page],
        }
