"""网关 SSE 流式协议契约。

本模块负责集中定义 SSE 帧格式、协议版本和错误/文本/元数据帧工厂。它不
负责生成业务答案或解析前端请求。
"""

from __future__ import annotations

import json
from typing import Any, Dict

PROTOCOL_VERSION = "gateway.sse.v1"

STATUS_TEXT = "text"
STATUS_INFO = "info"
STATUS_METADATA = "metadata"
STATUS_ERROR = "error"


def sse_encode(data: Dict[str, Any]) -> str:
    payload = {
        "protocol_version": PROTOCOL_VERSION,
        **data,
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def sse_done() -> str:
    return "data: [DONE]\n\n"


def text_frame(text: str, **metadata: Any) -> str:
    return sse_encode(
        {
            "status": STATUS_TEXT,
            "event": STATUS_TEXT,
            "text": text,
            **metadata,
        }
    )


def info_frame(text: str, **metadata: Any) -> str:
    return sse_encode(
        {
            "status": STATUS_INFO,
            "event": STATUS_INFO,
            "text": text,
            **metadata,
        }
    )


def metadata_frame(**metadata: Any) -> str:
    return sse_encode(
        {
            "status": STATUS_METADATA,
            "event": STATUS_METADATA,
            "text": "",
            **metadata,
        }
    )


def error_frame(message: str, **metadata: Any) -> str:
    return sse_encode(
        {
            "status": STATUS_ERROR,
            "event": STATUS_ERROR,
            "text": "",
            "error": message,
            **metadata,
        }
    )


def contract_payload() -> Dict[str, Any]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "stream": {
            "transport": "server_sent_events",
            "done_sentinel": "[DONE]",
            "statuses": [STATUS_TEXT, STATUS_INFO, STATUS_METADATA, STATUS_ERROR],
            "required_fields": ["protocol_version", "status", "event", "text"],
            "compatibility": "top-level fields are preserved for existing clients",
        },
    }
