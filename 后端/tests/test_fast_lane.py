from __future__ import annotations

import json

import pytest

from src.core.schemas import GatewayRequest


def request(question: str, *, tenant_id: str = "tenant-1", department: str = "general") -> GatewayRequest:
    return GatewayRequest(
        user_id="user-1",
        tenant_id=tenant_id,
        department=department,
        question=question,
        session_id="session-1",
    )


@pytest.mark.asyncio
async def test_calculator_answers_safe_natural_language_expression() -> None:
    from src.application.fast_lane import FastLaneService

    result = await FastLaneService().try_answer(request("请计算 2 * (3 + 4)"))

    assert result is not None
    assert result.source == "calculator"
    assert result.answer == "计算结果: 14"


@pytest.mark.asyncio
async def test_calculator_does_not_claim_request_without_expression() -> None:
    from src.application.fast_lane import FastLaneService

    result = await FastLaneService().try_answer(request("请调用工具计算一下"))

    assert result is None


@pytest.mark.asyncio
async def test_faq_requires_exact_normalized_tenant_and_department_match(tmp_path) -> None:
    from src.application.fast_lane import FastLaneService

    faq_path = tmp_path / "faq.json"
    faq_path.write_text(
        json.dumps(
            [
                {
                    "tenant_id": "tenant-1",
                    "department": "finance",
                    "question": "报销多久到账？",
                    "answer": "审核通过后五个工作日内到账。",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    service = FastLaneService(faq_path=faq_path)

    hit = await service.try_answer(request("  报销多久到账？ ", department="finance"))
    wrong_department = await service.try_answer(request("报销多久到账？", department="general"))

    assert hit is not None
    assert hit.source == "faq"
    assert hit.answer == "审核通过后五个工作日内到账。"
    assert wrong_department is None


@pytest.mark.asyncio
async def test_invalid_faq_file_degrades_to_no_match(tmp_path) -> None:
    from src.application.fast_lane import FastLaneService

    faq_path = tmp_path / "faq.json"
    faq_path.write_text("not-json", encoding="utf-8")

    result = await FastLaneService(faq_path=faq_path).try_answer(request("任意问题"))

    assert result is None
