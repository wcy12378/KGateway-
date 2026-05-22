"""BGE-Reranker 精排层 — CrossEncoder 交叉打分。"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("kgateway.core.reranker")


# ── 精排结果 ────────────────────────────────────────────────────

@dataclass
class RerankResult:
    """单条精排结果。"""

    doc_id: str
    rerank_score: float
    text: str
    metadata: Dict[str, Any]


# ── Reranker ────────────────────────────────────────────────────

@dataclass
class Reranker:
    """BGE-Reranker 精排序列。

    使用 sentence-transformers 的 CrossEncoder 对 query-doc 对进行
    二次交叉打分。通过 asyncio.to_thread 将 CPU 密集型推理卸载到线程池，
    绝不阻塞 FastAPI 主事件循环。

    属性：
        model_name: HuggingFace 模型名称。
        score_threshold: 最低分数阈值，低于此分数的文档被剔除。
        max_top_k: 最终返回的最大文档数。
    """

    model_name: str = "BAAI/bge-reranker-base"
    score_threshold: float = 0.35
    max_top_k: int = 3
    _model: Any = field(default=None, init=False, repr=False)
    _loaded: bool = field(default=False, init=False, repr=False)

    async def load_model(self) -> None:
        """异步加载 CrossEncoder 模型（通过线程池避免阻塞）。

        在线程池中执行模型加载，因为首次加载涉及大量磁盘 I/O 和权重初始化。
        """
        if self._loaded:
            return

        def _sync_load():
            from sentence_transformers import CrossEncoder
            model = CrossEncoder(self.model_name)
            return model

        try:
            self._model = await asyncio.to_thread(_sync_load)
            self._loaded = True
            logger.info("Reranker 模型加载成功: %s", self.model_name)
        except Exception as exc:
            logger.error("Reranker 模型加载失败: %s", exc)
            raise

    async def rerank_documents(
        self,
        *,
        query: str,
        docs: List[Dict[str, Any]],
    ) -> List[RerankResult]:
        """对 RRF 召回的文档进行交叉精排。

        核心安全设计：
        - CrossEncoder 推理通过 asyncio.to_thread 卸载到线程池
        - 评分 < score_threshold 的文档直接剔除
        - 最终只返回 top_k 条最相关文档

        Args:
            query: 用户原始查询。
            docs: RRF 融合后的候选文档列表，每项需含 doc_id, text, metadata。

        Returns:
            精排后的 RerankResult 列表（score >= threshold，最多 top_k 条）。
        """
        if not docs:
            return []

        if not self._loaded:
            await self.load_model()

        if self._model is None:
            logger.error("Reranker 模型未就绪，返回原始文档")
            return [
                RerankResult(
                    doc_id=d.get("doc_id", ""),
                    rerank_score=0.0,
                    text=d.get("text", ""),
                    metadata=d.get("metadata", {}),
                )
                for d in docs[: self.max_top_k]
            ]

        # 构建 query-doc 对
        pairs = [[query, d.get("text", "")] for d in docs]

        t0 = time.perf_counter()

        # 在线程池中执行推理（CPU 密集型，绝不阻塞事件循环）
        try:
            scores: List[float] = await asyncio.to_thread(
                self._model.predict, pairs
            )
        except Exception as exc:
            logger.error("Reranker 推理失败: %s", exc)
            raise

        latency_ms = (time.perf_counter() - t0) * 1000

        # 组装结果并过滤
        scored_docs: List[RerankResult] = []
        for doc, score in zip(docs, scores):
            score_val = float(score)
            if score_val >= self.score_threshold:
                scored_docs.append(
                    RerankResult(
                        doc_id=doc.get("doc_id", ""),
                        rerank_score=score_val,
                        text=doc.get("text", ""),
                        metadata=doc.get("metadata", {}),
                    )
                )

        # 按分数降序排列
        scored_docs.sort(key=lambda x: x.rerank_score, reverse=True)
        result = scored_docs[: self.max_top_k]

        logger.info(
            "Rerank 完成: input=%d above_threshold=%d output=%d latency=%.1fms",
            len(docs), len(scored_docs), len(result), latency_ms,
        )

        return result
