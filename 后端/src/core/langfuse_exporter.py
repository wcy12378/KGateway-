"""LangFuse 观测导出适配器。

本模块负责初始化 LangFuse 客户端并把本地 TraceContext 导出到 LangFuse。
它不负责本地 metrics 聚合、trace 生命周期管理或业务流程编排。
"""

from __future__ import annotations

import logging
from typing import Any

from src.config import config

logger = logging.getLogger("kagent.core.langfuse_exporter")


def init_langfuse_client() -> Any:
    """按配置初始化 LangFuse 客户端，失败时返回 None。"""

    try:
        from langfuse import Langfuse

        public_key = config.langfuse_public_key
        secret_key = config.langfuse_secret_key
        host = config.langfuse_host

        if public_key and secret_key:
            client = Langfuse(
                public_key=public_key,
                secret_key=secret_key,
                host=host,
            )
            logger.info("LangFuse 链路追踪已连接: %s", host)
            return client

        logger.info("LangFuse 未配置密钥，使用本地追踪模式")
        return None
    except ImportError:
        logger.info("langfuse 库未安装，使用本地追踪模式")
        return None
    except Exception as exc:
        logger.warning("LangFuse 初始化失败，降级为本地追踪: %s", exc)
        return None


def export_trace_to_langfuse(client: Any, ctx: Any) -> None:
    """把本地 trace 上下文同步导出到 LangFuse。"""

    try:
        trace = client.trace(
            id=ctx.trace_id,
            name="kagent_request",
            metadata={
                "tenant_id": ctx.tenant_id,
                "user_id": ctx.user_id,
                "cache_hit": ctx.cache_hit,
                "model_used": ctx.model_used,
            },
        )
        for name, span in ctx.spans.items():
            trace.generation(
                name=name,
                start_time=span.start_ms / 1000,
                end_time=span.end_ms / 1000 if span.end_ms else None,
                metadata=span.metadata,
                level="DEFAULT" if span.status == "ok" else "ERROR",
            )
    except Exception:
        return
