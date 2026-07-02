"""Qdrant 向量存储适配客户端。

本模块负责向量集合初始化、向量写入和相似度检索。它不负责租户策略判断、
答案生成或 HTTP/SSE 输出。
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from qdrant_client import AsyncQdrantClient, models

logger = logging.getLogger("kagent.db.qdrant")


def _scoped_point_id(point_id: str, payload: Dict[str, Any]) -> str:
    identity = (
        f"{payload['tenant_id']}\0{payload['department']}\0{point_id}"
    )
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"kagent-qdrant:{identity}"))


# ── 向量搜索结果 ────────────────────────────────────────────────

@dataclass
class VectorSearchResult:
    """单条向量检索结果。"""

    id: str
    score: float
    payload: Dict[str, Any]
    vector: Optional[List[float]] = None


# ── Qdrant 向量存储 ────────────────────────────────────────────

@dataclass
class QdrantVectorStore:
    """Qdrant 异步向量存储，强制执行多租户数据隔离。

    检索时通过 Qdrant 原生 Filter 在存储层硬过滤，而非检索后代码过滤，
    确保法务 / HR 等敏感部门数据在物理层面不可跨域访问。
    """

    url: str = field(default="http://localhost:6333")
    api_key: str = field(default="")
    collection: str = field(default="kagent_vectors")
    _client: Optional[AsyncQdrantClient] = field(default=None, init=False, repr=False)

    async def connect(self) -> None:
        """建立异步连接。"""
        try:
            self._client = AsyncQdrantClient(
                url=self.url,
                api_key=self.api_key if self.api_key else None,
            )
            # 验证连接
            await self._client.get_collections()
            logger.info("Qdrant 连接成功: %s", self.url)
        except Exception as exc:
            logger.error("Qdrant 连接失败: %s", exc)
            client = self._client
            self._client = None
            if client is not None:
                try:
                    await client.close()
                except Exception as close_exc:
                    logger.warning("Qdrant 失败连接关闭异常: %s", close_exc)
            raise

    async def close(self) -> None:
        """平滑关闭连接。"""
        if self._client is not None:
            await self._client.close()
            self._client = None
            logger.info("Qdrant 连接已关闭")

    @property
    def client(self) -> AsyncQdrantClient:
        if self._client is None:
            raise RuntimeError("Qdrant 未连接，请先调用 connect()")
        return self._client

    @property
    def connected(self) -> bool:
        """返回当前客户端是否已完成连接。"""
        return self._client is not None

    # ── 多租户硬过滤检索 ────────────────────────────────────────

    async def search_tenant_knowledge(
        self,
        *,
        tenant_id: str,
        department: str,
        query_vector: List[float],
        top_k: int = 5,
        extra_filter: Optional[models.Filter] = None,
    ) -> List[VectorSearchResult]:
        """检索指定租户 + 部门的知识库。

        核心安全设计：
        - 必须同时满足 tenant_id 和 department 两个硬过滤条件
        - 使用 Qdrant 原生 Filter，在向量索引层直接过滤，而非检索后过滤
        - 即使上层代码有 bug，存储层也绝不会泄露跨租户/跨部门数据
        """
        # 构造硬过滤条件：必须匹配 tenant_id AND department
        must_conditions = [
            models.FieldCondition(
                key="tenant_id",
                match=models.MatchValue(value=tenant_id),
            ),
            models.FieldCondition(
                key="department",
                match=models.MatchValue(value=department),
            ),
        ]

        # 合并额外的过滤条件（如果有）
        tenant_filter = models.Filter(
            must=must_conditions,
        )
        if extra_filter is not None:
            tenant_filter = models.Filter(
                must=[
                    tenant_filter,
                    extra_filter,
                ],
            )

        try:
            points = await self.client.query_points(
                collection_name=self.collection,
                query=query_vector,
                query_filter=tenant_filter,
                limit=top_k,
                with_payload=True,
                with_vectors=False,
            )
        except Exception as exc:
            logger.error(
                "Qdrant 检索失败: tenant=%s dept=%s err=%s",
                tenant_id, department, exc,
            )
            raise

        results: List[VectorSearchResult] = []
        for point in points.points:
            results.append(
                VectorSearchResult(
                    id=str(point.id),
                    score=point.score,
                    payload=point.payload or {},
                )
            )

        logger.info(
            "Qdrant 检索完成: tenant=%s dept=%s hits=%d top_score=%.4f",
            tenant_id,
            department,
            len(results),
            results[0].score if results else 0.0,
        )
        return results

    # ── 写入 ────────────────────────────────────────────────────

    async def upsert_point(
        self,
        *,
        point_id: str,
        vector: List[float],
        payload: Dict[str, Any],
    ) -> None:
        """写入或更新单个向量点。

        payload 中必须包含 tenant_id 和 department 字段，
        用于后续检索时的硬过滤。
        """
        if "tenant_id" not in payload or "department" not in payload:
            raise ValueError("payload 必须包含 tenant_id 和 department 字段")

        try:
            await self.client.upsert(
                collection_name=self.collection,
                points=[
                    models.PointStruct(
                        id=_scoped_point_id(point_id, payload),
                        vector=vector,
                        payload=payload,
                    ),
                ],
            )
            logger.info("Qdrant 写入成功: point=%s tenant=%s", point_id, payload.get("tenant_id"))
        except Exception as exc:
            logger.error("Qdrant 写入失败: point=%s err=%s", point_id, exc)
            raise

    async def upsert_batch(
        self,
        *,
        points: List[Dict[str, Any]],
        chunk_size: int = 100,
    ) -> int:
        """批量写入向量点。

        每个 point 字典需包含: id, vector, payload（含 tenant_id, department）。
        返回成功写入的数量。
        """
        written = 0
        for i in range(0, len(points), chunk_size):
            chunk = points[i : i + chunk_size]
            structs = []
            for p in chunk:
                payload = p.get("payload", {})
                if "tenant_id" not in payload or "department" not in payload:
                    raise ValueError(
                        f"point {p.get('id')} payload 缺少 tenant_id 或 department"
                    )
                structs.append(
                    models.PointStruct(
                        id=_scoped_point_id(str(p["id"]), payload),
                        vector=p["vector"],
                        payload=payload,
                    )
                )
            try:
                await self.client.upsert(
                    collection_name=self.collection,
                    points=structs,
                )
                written += len(structs)
            except Exception as exc:
                logger.error("Qdrant 批量写入失败: chunk_start=%d err=%s", i, exc)
                raise
        logger.info("Qdrant 批量写入完成: %d/%d points", written, len(points))
        return written
