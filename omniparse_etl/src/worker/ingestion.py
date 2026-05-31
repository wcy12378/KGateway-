"""Vector embedding & Qdrant ingestion — aligned with KGateway pre-filtering."""

from __future__ import annotations

import logging
import uuid
from typing import Any

import numpy as np
from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer

from src.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Embedding model (singleton, lazy-loaded)
# ---------------------------------------------------------------------------

_EMBED_MODEL_NAME = "BAAI/bge-large-zh-v1.5"
_embed_model: SentenceTransformer | None = None


def _get_embed_model() -> SentenceTransformer:
    global _embed_model
    if _embed_model is None:
        logger.info("Loading embedding model: %s", _EMBED_MODEL_NAME)
        _embed_model = SentenceTransformer(_EMBED_MODEL_NAME)
        logger.info("Embedding model loaded (dim=%d)", _embed_model.get_sentence_embedding_dimension())
    return _embed_model


# ---------------------------------------------------------------------------
# Qdrant client (singleton, lazy-loaded)
# ---------------------------------------------------------------------------

_qdrant: QdrantClient | None = None

# Must match KGateway's collection name for query alignment
COLLECTION_NAME = "kgateway_vectors"
# Must match the embedding dimension of BAAI/bge-large-zh-v1.5
VECTOR_DIM = 1024


def _get_qdrant() -> QdrantClient:
    global _qdrant
    if _qdrant is None:
        url = f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}"
        logger.info("Connecting to Qdrant: %s", url)
        _qdrant = QdrantClient(url=url)
    return _qdrant


def ensure_collection() -> None:
    """Create the collection if it doesn't exist, with payload indexes for
    tenant_id and department so KGateway's pre-filtering is fast."""
    client = _get_qdrant()
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME in existing:
        logger.info("Collection '%s' already exists", COLLECTION_NAME)
        return

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=models.VectorParams(
            size=VECTOR_DIM,
            distance=models.Distance.COSINE,
        ),
    )
    # Payload indexes for fast tenant / department filtering
    for field_name in ("tenant_id", "department"):
        client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name=field_name,
            field_schema=models.KeywordIndexParams(
                type="keyword",
                is_tenant=True,
            ),
        )
    logger.info("Collection '%s' created with tenant indexes", COLLECTION_NAME)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def embed_texts(texts: list[str]) -> list[list[float]]:
    """Encode a batch of texts into dense vectors."""
    model = _get_embed_model()
    vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return vectors.tolist()


def push_to_vector_db(
    chunks: list[dict[str, Any]],
    *,
    tenant_id: str,
    department: str,
) -> int:
    """Embed chunks and upsert into Qdrant.

    Each chunk dict must have:
        - page_content: str
        - metadata: dict (must include tenant_id, department, source_file, chunk_index)

    Returns the number of points successfully written.
    """
    if not chunks:
        logger.warning("No chunks to ingest")
        return 0

    ensure_collection()

    # Extract texts for batch embedding
    texts = [c["page_content"] for c in chunks]
    vectors = embed_texts(texts)

    # Build Qdrant points — tenant_id & department go into payload
    # for KGateway's pre-filtering (must match its FieldCondition keys)
    points: list[models.PointStruct] = []
    for vec, chunk in zip(vectors, chunks):
        meta = chunk.get("metadata", {})
        point_id = str(uuid.uuid4())
        payload = {
            "page_content": chunk["page_content"],
            "tenant_id": meta.get("tenant_id", tenant_id),
            "department": meta.get("department", department),
            "source_file": meta.get("source_file", ""),
            "chunk_index": meta.get("chunk_index", 0),
            "page_number": meta.get("page_number"),
            "source_type": meta.get("source_type", "text"),
        }
        points.append(models.PointStruct(id=point_id, vector=vec, payload=payload))

    # Batch upsert (100 points per batch to avoid memory spikes)
    client = _get_qdrant()
    written = 0
    batch_size = 100
    for i in range(0, len(points), batch_size):
        batch = points[i : i + batch_size]
        client.upsert(collection_name=COLLECTION_NAME, points=batch)
        written += len(batch)
        logger.debug("Upserted batch %d-%d", i, i + len(batch))

    logger.info(
        "Ingestion complete: %d points → collection='%s' tenant=%s dept=%s",
        written, COLLECTION_NAME, tenant_id, department,
    )
    return written
