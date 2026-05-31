"""Celery tasks — full ETL pipeline: download → parse → chunk → embed → ingest."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import requests
from celery import Celery

from src.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Celery app
# ---------------------------------------------------------------------------

celery_app = Celery(
    "omniparse_etl",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
)


# ---------------------------------------------------------------------------
# Pipeline stages (imported lazily to avoid slow cold-start)
# ---------------------------------------------------------------------------

def _parse_pdf(pdf_path: str | Path):
    from src.parsers.pdf_parser import MultimodalPDFParser
    parser = MultimodalPDFParser(strategy="hi_res", languages=["chi_sim", "eng"])
    return parser.parse(pdf_path)


def _chunk_documents(documents, *, tenant_id, department, source_file):
    from src.parsers.chunker import EnterpriseChunker
    chunker = EnterpriseChunker(chunk_size=800, chunk_overlap=150)
    return chunker.chunk_documents(
        documents,
        tenant_id=tenant_id,
        department=department,
        source_file=source_file,
    )


def _ingest_to_qdrant(chunks, *, tenant_id, department):
    from src.worker.ingestion import push_to_vector_db
    return push_to_vector_db(chunks, tenant_id=tenant_id, department=department)


# ---------------------------------------------------------------------------
# Helper: download file from presigned URL to a temp path
# ---------------------------------------------------------------------------

def _download_file(url: str) -> Path:
    """Stream-download a file from a presigned URL to a local temp file."""
    resp = requests.get(url, stream=True, timeout=300)
    resp.raise_for_status()

    # Infer extension from URL or Content-Type
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix or ".pdf"

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    for chunk in resp.iter_content(chunk_size=1024 * 1024):
        tmp.write(chunk)
    tmp.close()
    return Path(tmp.name)


# ---------------------------------------------------------------------------
# Main ETL task
# ---------------------------------------------------------------------------

@celery_app.task(name="parse_document", bind=True)
def parse_document_task(
    self,
    task_id: str,
    minio_url: str,
    tenant_id: str,
    department: str,
) -> dict:
    """Full ETL pipeline: download → parse → chunk → embed → push Qdrant.

    Stages:
        1. Download PDF from MinIO presigned URL
        2. Multimodal PDF parsing (text / table / image-caption)
        3. Format-aware chunking (tables never split)
        4. Embedding + Qdrant upsert with tenant metadata
    """
    local_path: Path | None = None
    try:
        # ── Stage 1: Download ─────────────────────────────────────
        logger.info("[ETL] Stage 1 — downloading from %s", minio_url[:80])
        self.update_state(state="DOWNLOADING", meta={"stage": "download"})
        local_path = _download_file(minio_url)
        logger.info("[ETL] Downloaded to %s (%d bytes)", local_path, local_path.stat().st_size)

        # ── Stage 2: Parse ───────────────────────────────────────
        logger.info("[ETL] Stage 2 — parsing PDF")
        self.update_state(state="PARSING", meta={"stage": "parse"})
        documents = _parse_pdf(local_path)
        logger.info("[ETL] Parsed %d elements", len(documents))

        # ── Stage 3: Chunk ───────────────────────────────────────
        logger.info("[ETL] Stage 3 — chunking documents")
        self.update_state(state="CHUNKING", meta={"stage": "chunk"})
        source_file = local_path.name
        chunks = _chunk_documents(
            documents,
            tenant_id=tenant_id,
            department=department,
            source_file=source_file,
        )
        logger.info("[ETL] Produced %d chunks", len(chunks))

        # ── Stage 4: Embed + Ingest ──────────────────────────────
        logger.info("[ETL] Stage 4 — embedding & pushing to Qdrant")
        self.update_state(state="INGESTING", meta={"stage": "ingest"})
        written = _ingest_to_qdrant(chunks, tenant_id=tenant_id, department=department)
        logger.info("[ETL] Ingested %d points", written)

        # ── Done ─────────────────────────────────────────────────
        result = {
            "task_id": task_id,
            "tenant_id": tenant_id,
            "department": department,
            "status": "SUCCESS",
            "elements_parsed": len(documents),
            "chunks_produced": len(chunks),
            "points_written": written,
        }
        logger.info("[ETL] Pipeline complete: %s", result)
        return result

    except Exception as exc:
        logger.exception("[ETL] Pipeline failed at task %s", task_id)
        self.update_state(state="FAILURE", meta={"error": str(exc)})
        raise

    finally:
        if local_path and local_path.exists():
            local_path.unlink(missing_ok=True)
            logger.debug("[ETL] Cleaned up temp file %s", local_path)
