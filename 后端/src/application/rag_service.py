"""应用层 RAG 检索服务。

本模块负责组织 Qdrant dense、BM25、RRF 融合和 reranker 流程，并向 Agent
提供统一检索能力。它不负责 HTTP 传输、模型流式生成或前端展示。
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.application.policies import TenantIsolationPolicy
from src.core.fusion import reciprocal_rank_fusion
from src.core.reranker import Reranker, RerankResult
from src.db.bm25_client import SparseRetriever
from src.db.qdrant_client import QdrantVectorStore

logger = logging.getLogger("kagent.application.rag")


@dataclass
class HybridRagService:
    """Hybrid Dense + BM25 + RRF + rerank pipeline."""

    bm25_retriever: Optional[SparseRetriever] = None
    reranker: Optional[Reranker] = None
    qdrant_store: Optional[QdrantVectorStore] = None
    isolation_policy: TenantIsolationPolicy = field(default_factory=TenantIsolationPolicy)

    async def _sparse_search(
        self,
        query: str,
        tenant_id: str,
        department: str,
        top_k: int = 20,
    ) -> List[Dict[str, Any]]:
        """在线程池执行同步 BM25 检索，避免阻塞 FastAPI 事件循环。"""
        if self.bm25_retriever is None:
            return []
        _ = self.isolation_policy.retrieval_scope(tenant_id, department)
        hits = await asyncio.to_thread(
            self.bm25_retriever.search,
            tenant_id=tenant_id,
            department=department,
            query=query,
            top_k=top_k,
        )
        return [
            {
                "doc_id": hit.doc_id,
                "bm25_score": hit.score,
                "text": hit.metadata.get("text", ""),
                "metadata": hit.metadata,
            }
            for hit in hits
        ]

    async def _dense_search(
        self,
        query: str,
        tenant_id: str,
        department: str,
        top_k: int = 20,
    ) -> List[Dict[str, Any]]:
        """执行带租户和部门硬过滤的真实 Qdrant 向量检索。"""
        if self.qdrant_store is None or not self.qdrant_store.connected:
            logger.warning("Qdrant 未连接，跳过 dense 检索")
            return []

        try:
            from src.core.embedder import embed_text

            query_vector = await asyncio.to_thread(embed_text, query)
            results = await self.qdrant_store.search_tenant_knowledge(
                tenant_id=tenant_id,
                department=department,
                query_vector=query_vector,
                top_k=top_k,
            )
        except Exception as exc:
            logger.warning("Qdrant dense 检索失败，降级为空结果: %s", exc)
            return []

        return [
            {
                "doc_id": str(result.payload.get("doc_id") or result.id),
                "vector_score": result.score,
                "text": result.payload.get("text", ""),
                "metadata": result.payload,
            }
            for result in results
        ]

    async def retrieve(
        self,
        *,
        query: str,
        tenant_id: str,
        department: str,
        top_k: int = 3,
    ) -> tuple[List[RerankResult], Dict[str, Any]]:
        rag_metrics: Dict[str, Any] = {}

        t_dense_start = time.perf_counter()
        dense_task = asyncio.create_task(
            self._dense_search(
                query=query,
                tenant_id=tenant_id,
                department=department,
                top_k=20,
            )
        )
        sparse_task = asyncio.create_task(
            self._sparse_search(
                query=query,
                tenant_id=tenant_id,
                department=department,
                top_k=20,
            )
        )

        dense_results, sparse_results = await asyncio.gather(dense_task, sparse_task)
        rag_metrics["dense_latency_ms"] = round((time.perf_counter() - t_dense_start) * 1000, 2)
        rag_metrics["dense_hits"] = len(dense_results)
        rag_metrics["sparse_hits"] = len(sparse_results)

        fused = reciprocal_rank_fusion(
            dense_results=dense_results,
            sparse_results=sparse_results,
            k=60,
            top_k=20,
        )
        rag_metrics["rrf_candidates"] = len(fused)

        rerank_input = [
            {
                "doc_id": doc.doc_id,
                "text": doc.metadata.get("text", doc.doc_id) if doc.metadata else doc.doc_id,
                "metadata": doc.metadata or {},
            }
            for doc in fused
        ]

        if self.reranker is not None:
            try:
                rerank_results = await self.reranker.rerank_documents(
                    query=query,
                    docs=rerank_input,
                )
            except Exception as exc:
                logger.warning("Reranker 不可用，降级为 RRF 排序: %s", exc)
                rerank_results = []
        else:
            rerank_results = []

        if not rerank_results:
            rerank_results = [
                RerankResult(
                    doc_id=doc.doc_id,
                    rerank_score=doc.rrf_score,
                    text=doc.metadata.get("text", "") if doc.metadata else "",
                    metadata=doc.metadata or {},
                )
                for doc in fused[:top_k]
            ]

        rag_metrics["rerank_output"] = len(rerank_results)
        return rerank_results, rag_metrics
