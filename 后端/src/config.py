"""项目环境配置模块。

本模块负责从环境变量读取 KAgent 运行配置，并提供统一配置对象。它不负责
初始化服务、执行业务流程或校验前端输入。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict

from pydantic import BaseModel, Field


class ModelPricing(BaseModel):
    input_price_per_1k: float = Field(..., gt=0)
    output_price_per_1k: float = Field(..., gt=0)


DEFAULT_MODEL_PRICING: Dict[str, ModelPricing] = {
    "qwen3-8b-instruct": ModelPricing(input_price_per_1k=0.0001, output_price_per_1k=0.0002),
    "deepseek-r1": ModelPricing(input_price_per_1k=0.0014, output_price_per_1k=0.0028),
    "claude-3.5-sonnet": ModelPricing(input_price_per_1k=0.003, output_price_per_1k=0.015),
}

ADVANCED_REASONING_KEYWORDS_THRESHOLD: int = 2000


@dataclass
class GatewayConfig:
    project_root: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent)
    debug: bool = field(default_factory=lambda: os.getenv("KAGENT_DEBUG", "false").lower() in ("1", "true", "yes"))

    database_url: str = field(default_factory=lambda: os.getenv("KAGENT_DATABASE_URL", "sqlite+aiosqlite:///data/gateway.db"))

    qdrant_url: str = field(default_factory=lambda: os.getenv("QDRANT_URL", "http://localhost:6333"))
    qdrant_api_key: str = field(default_factory=lambda: os.getenv("QDRANT_API_KEY", ""))
    qdrant_collection: str = field(default_factory=lambda: os.getenv("QDRANT_COLLECTION", "kagent_vectors"))

    neo4j_uri: str = field(default_factory=lambda: os.getenv("NEO4J_URI", "bolt://localhost:7687"))
    neo4j_user: str = field(default_factory=lambda: os.getenv("NEO4J_USER", "neo4j"))
    neo4j_password: str = field(default_factory=lambda: os.getenv("NEO4J_PASSWORD", ""))

    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379"))
    redis_cache_ttl_hours: int = field(default_factory=lambda: int(os.getenv("REDIS_CACHE_TTL_HOURS", "12")))
    redis_cache_threshold: float = field(default_factory=lambda: float(os.getenv("REDIS_CACHE_THRESHOLD", "0.2")))
    cache_namespace_version: str = field(
        default_factory=lambda: os.getenv("KAGENT_CACHE_NAMESPACE_VERSION", "v1").strip() or "v1"
    )

    circuit_breaker_threshold: int = field(default_factory=lambda: int(os.getenv("CB_FAILURE_THRESHOLD", "5")))
    circuit_breaker_timeout: int = field(default_factory=lambda: int(os.getenv("CB_RECOVERY_TIMEOUT", "60")))

    langfuse_public_key: str = field(default_factory=lambda: os.getenv("LANGFUSE_PUBLIC_KEY", ""))
    langfuse_secret_key: str = field(default_factory=lambda: os.getenv("LANGFUSE_SECRET_KEY", ""))
    langfuse_host: str = field(default_factory=lambda: os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"))

    jwt_secret: str = field(default_factory=lambda: os.getenv("JWT_SECRET", "dev-secret-change-in-production!"))
    jwt_algorithm: str = field(default_factory=lambda: os.getenv("JWT_ALGORITHM", "HS256"))
    jwt_issuer: str = field(default_factory=lambda: os.getenv("JWT_ISSUER", "kagent"))
    jwt_audience: str = field(default_factory=lambda: os.getenv("JWT_AUDIENCE", "kagent-api"))
    jwt_expire_hours: int = field(default_factory=lambda: int(os.getenv("JWT_EXPIRE_HOURS", "24")))
    allow_dev_tokens: bool = field(
        default_factory=lambda: os.getenv("KAGENT_ALLOW_DEV_TOKENS", "false").lower() in ("1", "true", "yes")
    )

    # Rate Limiting
    rate_limit_enabled: bool = field(
        default_factory=lambda: os.getenv("KAGENT_RATE_LIMIT_ENABLED", "true").lower() in ("1", "true", "yes")
    )
    rate_limit_per_minute: int = field(
        default_factory=lambda: int(os.getenv("KAGENT_RATE_LIMIT_PER_MINUTE", "30"))
    )

    # 可选的 Server-to-Server API Key
    api_key: str = field(default_factory=lambda: os.getenv("KAGENT_API_KEY", ""))

    # 工具调用审计环形缓冲区容量
    audit_max_entries: int = field(
        default_factory=lambda: int(os.getenv("KAGENT_AUDIT_MAX_ENTRIES", "1000"))
    )

    # 格式: name:command:arg1|arg2;name2:command2:arg1
    mcp_servers: str = field(default_factory=lambda: os.getenv("KAGENT_MCP_SERVERS", ""))

    # LLM Providers
    kagent_llm_provider: str = field(default_factory=lambda: os.getenv("KAGENT_LLM_PROVIDER", "deepseek"))
    provider_routing_strategy: str = field(
        default_factory=lambda: os.getenv("KAGENT_ROUTING_STRATEGY", "priority").strip().lower()
    )

    deepseek_api_url: str = field(default_factory=lambda: os.getenv("KAGENT_DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions"))
    deepseek_api_key: str = field(default_factory=lambda: os.getenv("KAGENT_DEEPSEEK_API_KEY", ""))
    deepseek_model: str = field(default_factory=lambda: os.getenv("KAGENT_DEEPSEEK_MODEL", "deepseek-chat"))

    openai_api_url: str = field(default_factory=lambda: os.getenv("KAGENT_OPENAI_API_URL", "https://api.openai.com/v1/chat/completions"))
    openai_api_key: str = field(default_factory=lambda: os.getenv("KAGENT_OPENAI_API_KEY", ""))
    openai_model: str = field(default_factory=lambda: os.getenv("KAGENT_OPENAI_MODEL", "gpt-4o-mini"))

    gemini_api_key: str = field(default_factory=lambda: os.getenv("KAGENT_GEMINI_API_KEY", ""))
    gemini_model: str = field(default_factory=lambda: os.getenv("KAGENT_GEMINI_MODEL", "gemini-2.0-flash"))

    # deprecated：保留旧字段以兼容现有调用方。
    llm_api_url: str = field(default_factory=lambda: os.getenv("LLM_API_URL", "https://api.deepseek.com/v1/chat/completions"))
    llm_api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "deepseek-chat"))

    embedding_model_name: str = field(default_factory=lambda: os.getenv("EMBEDDING_MODEL", "BAAI/bge-base-zh-v1.5"))
    embedding_warmup_enabled: bool = field(
        default_factory=lambda: os.getenv("KAGENT_EMBEDDING_WARMUP", "true").lower() in ("1", "true", "yes")
    )
    semantic_cache_timeout_ms: int = field(
        default_factory=lambda: int(os.getenv("KAGENT_CACHE_TIMEOUT_MS", "300"))
    )
    interactive_max_tokens: int = field(
        default_factory=lambda: int(os.getenv("KAGENT_INTERACTIVE_MAX_TOKENS", "512"))
    )
    workflow_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("KAGENT_WORKFLOW_TIMEOUT_SECONDS", "120"))
    )
    fast_path_enabled: bool = field(
        default_factory=lambda: os.getenv("KAGENT_FAST_PATH_ENABLED", "true").lower() in ("1", "true", "yes")
    )
    faq_path: Path = field(
        default_factory=lambda: Path(
            os.getenv(
                "KAGENT_FAQ_PATH",
                str(Path(__file__).resolve().parent.parent / "config" / "faq.json"),
            )
        )
    )

    model_pricing: Dict[str, ModelPricing] = field(default_factory=lambda: DEFAULT_MODEL_PRICING.copy())

    advanced_reasoning_threshold: int = field(
        default_factory=lambda: int(os.getenv("KAGENT_ADV_THRESHOLD", str(ADVANCED_REASONING_KEYWORDS_THRESHOLD)))
    )

    def pricing_for(self, model_name: str) -> ModelPricing:
        if model_name in self.model_pricing:
            return self.model_pricing[model_name]
        return max(self.model_pricing.values(), key=lambda p: p.output_price_per_1k)

    def validate_security(self) -> None:
        """拒绝生产环境使用公开或过短的 JWT 密钥。"""
        insecure_default = self.jwt_secret == "dev-secret-change-in-production!"
        if not (self.debug or self.allow_dev_tokens) and (
            insecure_default or len(self.jwt_secret.encode("utf-8")) < 32
        ):
            raise ValueError("JWT_SECRET 必须设置为至少 32 字节的随机密钥")

    def validate_runtime(self) -> None:
        """集中校验会影响资源与超时行为的运行参数。"""
        positive_values = {
            "REDIS_CACHE_TTL_HOURS": self.redis_cache_ttl_hours,
            "KAGENT_CACHE_TIMEOUT_MS": self.semantic_cache_timeout_ms,
            "KAGENT_INTERACTIVE_MAX_TOKENS": self.interactive_max_tokens,
            "KAGENT_WORKFLOW_TIMEOUT_SECONDS": self.workflow_timeout_seconds,
            "CB_FAILURE_THRESHOLD": self.circuit_breaker_threshold,
            "KAGENT_RATE_LIMIT_PER_MINUTE": self.rate_limit_per_minute,
            "KAGENT_AUDIT_MAX_ENTRIES": self.audit_max_entries,
            "KAGENT_ADV_THRESHOLD": self.advanced_reasoning_threshold,
        }
        for name, value in positive_values.items():
            if float(value) <= 0:
                raise ValueError(f"{name} 必须大于 0")
        if self.circuit_breaker_timeout < 0:
            raise ValueError("CB_RECOVERY_TIMEOUT 不能小于 0")
        if not 0 <= self.redis_cache_threshold <= 2:
            raise ValueError("REDIS_CACHE_THRESHOLD 必须在 0-2 之间")


config = GatewayConfig()
