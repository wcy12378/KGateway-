"""Enterprise-grade format-aware document chunker.

Core design principles:
1. Tables (Markdown / HTML) are NEVER split — they become standalone chunks.
2. Regular text goes through a sliding-window splitter.
3. Every output chunk carries tenant-isolation + source metadata.
"""

from __future__ import annotations

import re
import logging
from dataclasses import asdict
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.parsers.pdf_parser import Document

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Table detection patterns
# ---------------------------------------------------------------------------

# Markdown table: lines starting with |, or separator lines like |---|---|
_MD_TABLE_START = re.compile(r"^\s*\|", re.MULTILINE)
_MD_TABLE_SEP = re.compile(r"^\s*\|[\s\-:|]+\|\s*$", re.MULTILINE)

# HTML table wrapper
_HTML_TABLE = re.compile(r"<table[\s>]", re.IGNORECASE)


def _is_table_block(text: str) -> bool:
    """Return True if the entire text block looks like a table."""
    stripped = text.strip()
    if not stripped:
        return False
    # HTML table
    if _HTML_TABLE.search(stripped):
        return True
    # Markdown table: must have at least a header row and a separator row
    lines = stripped.splitlines()
    if len(lines) >= 2:
        pipe_lines = sum(1 for l in lines if _MD_TABLE_START.match(l))
        sep_lines = sum(1 for l in lines if _MD_TABLE_SEP.match(l))
        if sep_lines >= 1 and pipe_lines >= 2:
            return True
    return False


# ---------------------------------------------------------------------------
# EnterpriseChunker
# ---------------------------------------------------------------------------

class EnterpriseChunker:
    """Format-aware chunker that protects tables and injects metadata."""

    def __init__(
        self,
        chunk_size: int = 800,
        chunk_overlap: int = 150,
        separators: list[str] | None = None,
    ) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=separators or ["\n\n", "\n", "。", ".", " ", ""],
        )

    # ------------------------------------------------------------------
    # public
    # ------------------------------------------------------------------

    def chunk_documents(
        self,
        documents: list[Document],
        *,
        tenant_id: str,
        department: str,
        source_file: str,
    ) -> list[dict[str, Any]]:
        """Split documents into chunks with full metadata injection.

        Returns a flat list of dicts ready for vector-store ingestion.
        """
        raw_chunks: list[dict[str, Any]] = []

        for doc in documents:
            text = doc.page_content
            meta = doc.metadata
            el_type = meta.get("type", "text")

            # ---- TABLE DEFENSE: keep whole ----
            if el_type == "table" or _is_table_block(text):
                raw_chunks.append(self._make_entry(
                    text=text,
                    page_number=meta.get("page_number"),
                    source_type="table",
                ))
                continue

            # ---- IMAGE CAPTION: already short, keep whole ----
            if el_type == "image_caption":
                raw_chunks.append(self._make_entry(
                    text=text,
                    page_number=meta.get("page_number"),
                    source_type="image_caption",
                ))
                continue

            # ---- NORMAL TEXT: sliding-window split ----
            for sub in self._splitter.split_text(text):
                raw_chunks.append(self._make_entry(
                    text=sub,
                    page_number=meta.get("page_number"),
                    source_type="text",
                ))

        # Inject tenant / source metadata + sequential chunk_index
        return self._stamp_metadata(
            raw_chunks,
            tenant_id=tenant_id,
            department=department,
            source_file=source_file,
        )

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------

    @staticmethod
    def _make_entry(*, text: str, page_number: int | None, source_type: str) -> dict:
        return {
            "page_content": text,
            "page_number": page_number,
            "source_type": source_type,
        }

    @staticmethod
    def _stamp_metadata(
        chunks: list[dict],
        *,
        tenant_id: str,
        department: str,
        source_file: str,
    ) -> list[dict]:
        stamped: list[dict] = []
        for idx, c in enumerate(chunks):
            stamped.append({
                "page_content": c["page_content"],
                "metadata": {
                    "tenant_id": tenant_id,
                    "department": department,
                    "source_file": source_file,
                    "chunk_index": idx,
                    "page_number": c.get("page_number"),
                    "source_type": c.get("source_type", "text"),
                },
            })
        return stamped
