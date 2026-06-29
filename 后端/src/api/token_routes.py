"""开发与测试环境使用的 Token 签发路由。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from src.api.auth import create_token
from src.config import config
from src.core.schemas import Department

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class TokenRequest(BaseModel):
    """开发 token 所需的用户身份。"""

    user_id: str = Field(min_length=1, max_length=128)
    tenant_id: str = Field(default="default_tenant", min_length=1, max_length=128)
    department: Department = Department.GENERAL


class TokenResponse(BaseModel):
    """Bearer token 响应。"""

    access_token: str
    token_type: str = "Bearer"


@router.post("/token", response_model=TokenResponse)
async def issue_token(req: TokenRequest) -> TokenResponse:
    """签发开发测试 token；生产环境应替换为 SSO/OAuth。"""
    if not config.allow_dev_tokens:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    token = create_token(
        user_id=req.user_id,
        tenant_id=req.tenant_id,
        department=req.department.value,
        expires_in=config.jwt_expire_hours * 3600,
    )
    return TokenResponse(access_token=token)
