"""RRF (Reciprocal Rank Fusion) 多路召回融合算法。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List

logger = logging.getLogger("kgateway.core.fusion")


# ── 融合候选文档 ────────────────────────────────────────────────

@dataclass
class FusedDocument:
    """融合后的文档条目。"""

    doc_id: str
    rrf_score: float
    dense_score: float = 0.0
    bm25_score: float = 0.0
    dense_rank: int = 0
    bm25_rank: int = 0
    metadata: Dict[str, Any] | None = None


# ── RRF 融合 ────────────────────────────────────────────────────

def reciprocal_rank_fusion(
    dense_results: List[Dict[str, Any]],
    sparse_results: List[Dict[str, Any]],
    *,
    k: int = 60,
    top_k: int = 20,
) -> List[FusedDocument]:
    """倒数排名融合（Reciprocal Rank Fusion）。

    工业级标准公式：
        RRF_Score(d) = Σ_{m∈M} 1 / (k + r_m(d))

    其中：
        - k = 60（平滑常数，防止排名靠后的文档权重过高）
        - r_m(d) = 文档 d 在第 m 个检索器中的排名（从 1 开始）

    Args:
        dense_results: Dense 检索结果列表，每项需含 doc_id 和 vector_score。
        sparse_results: Sparse 检索结果列表，每项需含 doc_id 和 bm25_score。
        k: 平滑常数，默认 60。
        top_k: 返回融合后排名前 top_k 的文档。

    Returns:
        按 RRF 分数降序排列的 FusedDocument 列表。
    """
    # ── 构建排名映射 ────────────────────────────────────────────
    # Dense 榜单：按 vector_score 降序排名
    dense_ranked: Dict[str, int] = {}
    dense_scores: Dict[str, float] = {}
    dense_metas: Dict[str, Dict[str, Any]] = {}
    for rank, doc in enumerate(dense_results, start=1):
        doc_id = doc["doc_id"]
        dense_ranked[doc_id] = rank
        dense_scores[doc_id] = doc.get("vector_score", 0.0)
        dense_metas[doc_id] = doc.get("metadata", {})

    # Sparse 榜单：按 bm25_score 降序排名
    sparse_ranked: Dict[str, int] = {}
    sparse_scores: Dict[str, float] = {}
    sparse_metas: Dict[str, Dict[str, Any]] = {}
    for rank, doc in enumerate(sparse_results, start=1):
        doc_id = doc["doc_id"]
        sparse_ranked[doc_id] = rank
        sparse_scores[doc_id] = doc.get("bm25_score", 0.0)
        sparse_metas[doc_id] = doc.get("metadata", {})

    # ── 合并所有候选文档 ────────────────────────────────────────
    all_doc_ids = set(dense_ranked.keys()) | set(sparse_ranked.keys())

    fused: List[FusedDocument] = []
    for doc_id in all_doc_ids:
        rrf_score = 0.0
        d_rank = dense_ranked.get(doc_id)
        s_rank = sparse_ranked.get(doc_id)

        if d_rank is not None:
            rrf_score += 1.0 / (k + d_rank)
        if s_rank is not None:
            rrf_score += 1.0 / (k + s_rank)

        # 取较新的 metadata（dense 优先）
        metadata = dense_metas.get(doc_id) or sparse_metas.get(doc_id) or {}

        fused.append(
            FusedDocument(
                doc_id=doc_id,
                rrf_score=rrf_score,
                dense_score=dense_scores.get(doc_id, 0.0),
                bm25_score=sparse_scores.get(doc_id, 0.0),
                dense_rank=d_rank or 0,
                bm25_rank=s_rank or 0,
                metadata=metadata,
            )
        )

    # ── 降序排列 ────────────────────────────────────────────────
    fused.sort(key=lambda x: x.rrf_score, reverse=True)

    # 截取前 top_k
    result = fused[:top_k]

    logger.info(
        "RRF 融合完成: dense=%d sparse=%d merged=%d output=%d k=%d",
        len(dense_results),
        len(sparse_results),
        len(fused),
        len(result),
        k,
    )

    return result
