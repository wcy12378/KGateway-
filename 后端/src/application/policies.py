"""应用层策略对象。

本模块负责封装模型路由、租户隔离等可替换业务规则。它不负责执行请求流程、
访问数据库或输出 HTTP/SSE 响应。
"""

from __future__ import annotations

from dataclasses import dataclass

from src.config import config
from src.core.schemas import GatewayRequest


@dataclass(frozen=True)
class ModelRoutingPolicy:
    """Pure routing policy independent of transport and storage."""

    advanced_reasoning_threshold: int = config.advanced_reasoning_threshold

    def select_model(self, request: GatewayRequest) -> str:
        if request.advanced_reasoning:
            return self._pick_advanced()
        if len(request.question) > self.advanced_reasoning_threshold:
            return self._pick_advanced()
        return "qwen3-8b-instruct"

    def _pick_advanced(self) -> str:
        return "deepseek-r1"


@dataclass(frozen=True)
class TenantIsolationPolicy:
    """Strategy object for tenant/department scoping."""

    def cache_namespace(self, tenant_id: str) -> str:
        return f"kagent:cache:{tenant_id}"

    def retrieval_scope(self, tenant_id: str, department: str) -> dict[str, str]:
        return {"tenant_id": tenant_id, "department": department}
