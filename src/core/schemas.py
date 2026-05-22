"""统一网关请求 / 响应 Schema。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class Department(str, Enum):
    """部门枚举 — 控制数据隔离策略。"""

    LEGAL = "legal"        # 法务
    HR = "hr"              # 人力资源
    ENGINEERING = "engineering"
    FINANCE = "finance"
    GENERAL = "general"


class GatewayRequest(BaseModel):
    """网关统一请求体。

    所有进入网关的请求必须携带此结构，路由层据此做分发决策。
    """

    user_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
   
        examples=["user_001"],
    )
    tenant_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
     
        examples=["tenant_acme"],
    )
    department: Department = Field(
        default=Department.GENERAL,

    )
    question: str = Field(
        ...,
        min_length=1,
        max_length=100_000,
        description="用户提出的问题",
        examples=["请解释一下最新的劳动法修订内容"],
    )
    session_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="会话 ID，用于上下文追踪",
    )
    advanced_reasoning: bool = Field(
        default=False,
        description="是否启用高级推理（路由到更强模型）",
    )

    @field_validator("question")
    @classmethod
    def question_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("question 不能为空白字符串")
        return v.strip()


class GatewayResponse(BaseModel):
    """网关统一响应体。"""

    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    model_used: str
    answer: str
    token_input: int = 0
    token_output: int = 0
    estimated_cost_usd: float = 0.0
    latency_ms: float = 0.0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GatewayError(BaseModel):
    """网关错误响应。"""

    code: str
    message: str
    detail: Optional[str] = None
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
