"""网关请求与响应数据模型。

本模块负责定义跨 API、应用层和前端契约共用的数据结构。它不包含业务流程、
数据库访问或模型调用实现。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class Department(str, Enum):
    LEGAL = "legal"
    HR = "hr"
    ENGINEERING = "engineering"
    FINANCE = "finance"
    GENERAL = "general"


class GatewayRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128, examples=["user_001"])
    tenant_id: str = Field(..., min_length=1, max_length=128, examples=["tenant_acme"])
    department: Department = Field(default=Department.GENERAL)
    question: str = Field(..., min_length=1, max_length=100_000, description="User question")
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()), min_length=1, max_length=128)
    advanced_reasoning: bool = Field(default=False)

    @field_validator("question")
    @classmethod
    def question_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question cannot be blank")
        return value

    @field_validator("user_id", "tenant_id", "session_id")
    @classmethod
    def identity_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("identity field cannot be blank")
        return value


class GatewayResponse(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    model_used: str
    answer: str
    token_input: int = 0
    token_output: int = 0
    estimated_cost_usd: float = 0.0
    latency_ms: float = 0.0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GatewayWorkflowRequest(GatewayRequest):
    workflow_name: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z0-9_.-]+$",
        examples=["research"],
    )


class WorkflowStepResponse(BaseModel):
    agent_name: str
    status: str
    answer: str = ""
    duration_ms: float = 0.0
    total_tokens: int = 0
    error: Optional[str] = None


class GatewayWorkflowResponse(BaseModel):
    workflow_name: str
    mode: str
    status: str
    final_answer: str
    session_id: str
    steps: List[WorkflowStepResponse] = Field(default_factory=list)
    total_duration_ms: float = 0.0
    total_tokens: int = 0


class GatewayError(BaseModel):
    code: str
    message: str
    detail: Optional[str] = None
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
