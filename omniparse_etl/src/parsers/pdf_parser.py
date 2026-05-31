"""Multimodal PDF parser: text + table + image-caption extraction via unstructured."""

from __future__ import annotations

import hashlib
import io
import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from unstructured.partition.pdf import partition_pdf
from unstructured.documents.elements import (
    Element,
    NarrativeText,
    Table,
    Image,
    ListItem,
    Title,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Document model
# ---------------------------------------------------------------------------

@dataclass
class Document:
    page_content: str
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Simulated VLM (Vision-Language Model) captioner
# ---------------------------------------------------------------------------

class VLMSimulator:
    """Placeholder for a real VLM service (e.g. Qwen-VL, LLaVA, GPT-4V).

    In production this would POST the image bytes to an HTTP/gRPC endpoint.
    Here we return a deterministic pseudo-caption so the pipeline can be tested
    end-to-end without GPU dependencies.
    """

    def caption(self, image_bytes: bytes, mime: str = "image/png") -> str:
        digest = hashlib.md5(image_bytes).hexdigest()[:8]
        return (
            f"[VLM Caption] 图片 (md5={digest}, size={len(image_bytes)}B, "
            f"mime={mime}) — 此处为模拟描述，生产环境替换为真实 VLM 推理结果。"
        )


# ---------------------------------------------------------------------------
# Core parser
# ---------------------------------------------------------------------------

# Mapping from unstructured element class → our Document type tag
_ELEMENT_TYPE_MAP: dict[type, str] = {
    NarrativeText: "text",
    Title: "text",
    ListItem: "text",
    Table: "table",
    Image: "image_caption",
}


class MultimodalPDFParser:
    """Parse a PDF into a flat list of Documents with text / table / image-caption."""

    def __init__(
        self,
        *,
        strategy: str = "hi_res",
        languages: list[str] | None = None,
        vlm: VLMSimulator | None = None,
    ) -> None:
        self.strategy = strategy
        self.languages = languages or ["chi_sim", "eng"]
        self.vlm = vlm or VLMSimulator()

    # ------------------------------------------------------------------
    # public
    # ------------------------------------------------------------------

    def parse(self, file_path: str | Path) -> list[Document]:
        """Parse *file_path* and return a list of Documents in reading order."""
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(file_path)

        logger.info("partition_pdf start: %s (strategy=%s)", file_path, self.strategy)
        elements: list[Element] = partition_pdf(
            filename=str(file_path),
            strategy=self.strategy,
            languages=self.languages,
            include_page_break=True,
            include_metadata=True,
        )
        logger.info("partition_pdf done: %d elements", len(elements))

        return [self._element_to_doc(el) for el in elements]

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------

    def _element_to_doc(self, element: Element) -> Document:
        el_type = _ELEMENT_TYPE_MAP.get(type(element), "text")
        page_num = getattr(element.metadata, "page_number", None)

        if isinstance(element, Table):
            return self._handle_table(element, page_num)
        if isinstance(element, Image):
            return self._handle_image(element, page_num)
        return self._handle_text(element, el_type, page_num)

    def _handle_text(
        self, element: Element, el_type: str, page_num: int | None
    ) -> Document:
        return Document(
            page_content=element.text,
            metadata={"page_number": page_num, "type": el_type},
        )

    def _handle_table(self, element: Table, page_num: int | None) -> Document:
        """Tables are kept intact — never split into individual cells."""
        html = getattr(element, "text_as_html", None) or element.text
        return Document(
            page_content=html,
            metadata={
                "page_number": page_num,
                "type": "table",
                "format": "html",
            },
        )

    def _handle_image(self, element: Image, page_num: int | None) -> Document:
        """Extract image bytes, call VLM for caption, return caption as text."""
        image_bytes = self._extract_image_bytes(element)
        mime = getattr(element.metadata, "image_mime_type", "image/png") or "image/png"

        caption = self.vlm.caption(image_bytes, mime=mime)
        logger.debug("Image caption (page %s): %s", page_num, caption[:80])

        return Document(
            page_content=caption,
            metadata={
                "page_number": page_num,
                "type": "image_caption",
                "image_size_bytes": len(image_bytes),
            },
        )

    @staticmethod
    def _extract_image_bytes(element: Image) -> bytes:
        """Pull raw bytes from an Image element regardless of storage format."""
        # Case 1: bytes already loaded
        if hasattr(element, "image") and isinstance(element.image, bytes):
            return element.image

        # Case 2: path to extracted image on disk
        image_path = getattr(element.metadata, "image_path", None)
        if image_path and Path(image_path).is_file():
            return Path(image_path).read_bytes()

        # Case 3: embedded as base64 in metadata
        b64 = getattr(element.metadata, "image_base64", None)
        if b64:
            import base64
            return base64.b64decode(b64)

        return b""
