"""JWT 认证中间件。

本模块负责 JWT token 的签发、验证和 FastAPI 依赖注入。它不负责
用户管理、权限策略或业务编排。
"""

from __future__ import annotations

import hmac
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Optional

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.config import config

logger = logging.getLogger("kagent.api.auth")
_ALLOWED_DEPARTMENTS = {"legal", "hr", "engineering", "finance", "general"}

security_scheme = HTTPBearer(auto_error=False)


@dataclass
class TokenPayload:
    """JWT token 中携带的用户身份信息。"""

    user_id: str
    tenant_id: str
    department: str = "general"
    exp: float = 0.0


def create_token(
    user_id: str,
    tenant_id: str = "default_tenant",
    department: str = "general",
    expires_in: int = 86400,
) -> str:
    """签发 JWT token，默认有效期 24 小时。"""
    user_id = user_id.strip()
    tenant_id = tenant_id.strip()
    if not user_id or not tenant_id:
        raise ValueError("user_id 和 tenant_id 不能为空")
    now = time.time()
    payload = {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "department": department,
        "exp": now + expires_in,
        "iat": now,
        "jti": str(uuid.uuid4()),
        "iss": config.jwt_issuer,
        "aud": config.jwt_audience,
    }
    return jwt.encode(payload, config.jwt_secret, algorithm=config.jwt_algorithm)


def verify_token(token: str) -> TokenPayload:
    """验证 JWT token，解析出用户信息。"""
    try:
        payload = jwt.decode(
            token,
            config.jwt_secret,
            algorithms=[config.jwt_algorithm],
            issuer=config.jwt_issuer,
            audience=config.jwt_audience,
            options={
                "require": [
                    "user_id",
                    "tenant_id",
                    "department",
                    "exp",
                    "iat",
                    "jti",
                    "iss",
                    "aud",
                ]
            },
        )
        user_id = payload["user_id"]
        tenant_id = payload["tenant_id"]
        department = payload["department"]
        if not isinstance(user_id, str) or not user_id.strip():
            raise jwt.InvalidTokenError("user_id claim 无效")
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise jwt.InvalidTokenError("tenant_id claim 无效")
        if department not in _ALLOWED_DEPARTMENTS:
            raise jwt.InvalidTokenError("department claim 无效")
        return TokenPayload(
            user_id=user_id.strip(),
            tenant_id=tenant_id.strip(),
            department=department,
            exp=float(payload["exp"]),
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 已过期",
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 Token",
        ) from exc


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
) -> TokenPayload:
    """从请求头提取并验证当前用户。"""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少认证信息，请在请求头中添加 Authorization: Bearer <token>",
        )
    return verify_token(credentials.credentials)


def verify_api_key_value(x_api_key: Optional[str]) -> Optional[TokenPayload]:
    """验证 API Key，并返回受控的服务身份。"""
    if not config.api_key:
        return None
    if x_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少 X-API-Key 请求头",
        )
    if not hmac.compare_digest(x_api_key.encode("utf-8"), config.api_key.encode("utf-8")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 API Key",
        )
    return TokenPayload(
        user_id="api_key_client",
        tenant_id="default_tenant",
        department="general",
    )


async def verify_api_key(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> Optional[TokenPayload]:
    """FastAPI 依赖：API Key 未配置时跳过，配置后进行验证。"""
    return verify_api_key_value(x_api_key)


# 公开端点列表（不需要认证）。token 路由仅供开发与测试使用。
PUBLIC_PATHS = {
    "/health",
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
    "/openapi.json",
    "/api/v1/gateway/contract",
    "/api/v1/auth/token",
}
