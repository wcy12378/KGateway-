"""P1 Rate Limiting 与 API Key 认证测试。"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.api.auth import verify_api_key_value
from src.config import config
from src.main import app, limiter


def test_api_key_is_optional_when_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "api_key", "")
    assert verify_api_key_value(None) is None


def test_api_key_validation_and_service_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "api_key", "server-secret")

    with pytest.raises(HTTPException, match="缺少 X-API-Key"):
        verify_api_key_value(None)

    with pytest.raises(HTTPException, match="无效的 API Key"):
        verify_api_key_value("wrong-secret")

    with pytest.raises(HTTPException, match="无效的 API Key"):
        verify_api_key_value("无效密钥")

    identity = verify_api_key_value("server-secret")
    assert identity is not None
    assert identity.user_id == "api_key_client"
    assert identity.tenant_id == "default_tenant"
    assert identity.department == "general"


def test_api_key_authenticates_protected_route(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "api_key", "server-secret")
    limiter.reset()
    client = TestClient(app)
    response = client.get(
        "/api/v1/gateway/metrics",
        headers={"X-API-Key": "server-secret"},
    )
    client.close()
    limiter.reset()
    assert response.status_code == 200


def test_public_path_is_exempt_from_rate_limit() -> None:
    limiter.reset()
    client = TestClient(app)
    responses = [client.get("/health") for _ in range(config.rate_limit_per_minute + 2)]
    client.close()
    limiter.reset()
    assert all(response.status_code == 200 for response in responses)


def test_protected_path_returns_429_after_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "api_key", "server-secret")
    limiter.reset()
    client = TestClient(app)
    responses = [
        client.get(
            "/api/v1/gateway/metrics",
            headers={"X-API-Key": "server-secret"},
        )
        for _ in range(config.rate_limit_per_minute + 1)
    ]
    client.close()
    limiter.reset()
    assert responses[-1].status_code == 429
