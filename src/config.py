"""KGateway 环境变量与配置管理。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict

from pydantic import BaseModel, Field


class ModelPricing(BaseModel):
    """单个模型的 Token 定价（单位：USD / 1K tokens）。"""

    input_price_per_1k: float = Field(..., gt=0)  # 输入 Token 单价
output_price_per_1k: float = Field(..., gt=0)  # 输出 Token 单价

# ── 默认模型定价表 ──────────────────────────────────────────────
DEFAULT_MODEL_PRICING: Dict[str, ModelPricing] = {
    "qwen3-8b-instruct": ModelPricing(input_price_per_1k=0.0001, output_price_per_1k=0.0002),
    "deepseek-r1": ModelPricing(input_price_per_1k=0.0014, output_price_per_1k=0.0028),
    "claude-3.5-sonnet": ModelPricing(input_price_per_1k=0.003, output_price_per_1k=0.015),
}

# ── 路由阈值 ────────────────────────────────────────────────────
ADVANCED_REASONING_KEYWORDS_THRESHOLD: int = 2000  # 超过此字数触发高级推理模型


@dataclass
class GatewayConfig:
    """网关全局配置，从环境变量加载并提供安全默认值。"""

    # 基础
    project_root: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent)
    debug: bool = field(default_factory=lambda: os.getenv("KGW_DEBUG", "false").lower() in ("1", "true", "yes"))

    # 关系型数据库
    database_url: str = field(default_factory=lambda: os.getenv("KGW_DATABASE_URL", "sqlite+aiosqlite:///data/gateway.db"))

    # Qdrant 向量数据库
    qdrant_url: str = field(default_factory=lambda: os.getenv("QDRANT_URL", "http://localhost:6333"))
    qdrant_api_key: str = field(default_factory=lambda: os.getenv("QDRANT_API_KEY", ""))
    qdrant_collection: str = field(default_factory=lambda: os.getenv("QDRANT_COLLECTION", "kgateway_vectors"))

    # Neo4j 图数据库
    neo4j_uri: str = field(default_factory=lambda: os.getenv("NEO4J_URI", "bolt://localhost:7687"))
    neo4j_user: str = field(default_factory=lambda: os.getenv("NEO4J_USER", "neo4j"))
    neo4j_password: str = field(default_factory=lambda: os.getenv("NEO4J_PASSWORD", ""))

    # Redis 语义缓存
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379"))
    redis_cache_ttl_hours: int = field(default_factory=lambda: int(os.getenv("REDIS_CACHE_TTL_HOURS", "12")))
    redis_cache_threshold: float = field(default_factory=lambda: float(os.getenv("REDIS_CACHE_THRESHOLD", "0.96")))

    # 熔断器
    circuit_breaker_threshold: int = field(default_factory=lambda: int(os.getenv("CB_FAILURE_THRESHOLD", "5")))
    circuit_breaker_timeout: int = field(default_factory=lambda: int(os.getenv("CB_RECOVERY_TIMEOUT", "60")))

    # 模型定价
    model_pricing: Dict[str, ModelPricing] = field(default_factory=lambda: DEFAULT_MODEL_PRICING.copy())

    # 路由
    advanced_reasoning_threshold: int = field(
        default_factory=lambda: int(os.getenv("KGW_ADV_THRESHOLD", str(ADVANCED_REASONING_KEYWORDS_THRESHOLD)))
    )

    def pricing_for(self, model_name: str) -> ModelPricing:
        """获取指定模型的定价，不存在时返回最贵的兜底价格。"""
        if model_name in self.model_pricing:
            return self.model_pricing[model_name]
        # 兜底：取所有定价中的最高值，避免低估成本
        fallback = max(self.model_pricing.values(), key=lambda p: p.output_price_per_1k)
        return fallback


# 单例
config = GatewayConfig()
