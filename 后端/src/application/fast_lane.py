"""Safe deterministic responses that do not require an LLM call."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.core.schemas import GatewayRequest
from src.core.tools.builtin import calculator

logger = logging.getLogger("kagent.application.fast_lane")

_CALCULATION_REQUEST = re.compile(
    r"^(?:请)?(?:帮我)?(?:计算|算一下|算出)\s*[:：]?\s*(?P<expression>.+?)\s*[。？?]?$"
)
_SAFE_ARITHMETIC = re.compile(r"^[0-9\s+\-*/().]+$")


def _normalize_question(value: str) -> str:
    return " ".join(value.strip().lower().split())


@dataclass(frozen=True)
class FastLaneResult:
    answer: str
    source: str


class FastLaneService:
    def __init__(self, faq_path: Path | None = None) -> None:
        self._faq_entries = self._load_faq_entries(faq_path)

    @staticmethod
    def _load_faq_entries(faq_path: Path | None) -> list[dict[str, str]]:
        if faq_path is None or not faq_path.is_file():
            return []
        try:
            payload = json.loads(faq_path.read_text(encoding="utf-8"))
            if not isinstance(payload, list):
                raise ValueError("FAQ root must be a list")
            required = {"tenant_id", "department", "question", "answer"}
            return [
                {key: str(item[key]).strip() for key in required}
                for item in payload
                if isinstance(item, dict)
                and required.issubset(item)
                and all(str(item[key]).strip() for key in required)
            ]
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            logger.warning("FAQ fast lane disabled: %s", exc)
            return []

    async def try_answer(self, request: GatewayRequest) -> FastLaneResult | None:
        if request.advanced_reasoning:
            return None

        match = _CALCULATION_REQUEST.fullmatch(request.question.strip())
        if match:
            expression = match.group("expression").strip()
            if _SAFE_ARITHMETIC.fullmatch(expression) and any(char.isdigit() for char in expression):
                answer = await calculator(expression)
                if answer.startswith("计算结果:"):
                    return FastLaneResult(answer=answer, source="calculator")

        department = getattr(request.department, "value", request.department)
        normalized = _normalize_question(request.question)
        for entry in self._faq_entries:
            if (
                entry["tenant_id"] == request.tenant_id
                and entry["department"] == department
                and _normalize_question(entry["question"]) == normalized
            ):
                return FastLaneResult(answer=entry["answer"], source="faq")
        return None
