"""Redis 语义缓存适配能力。

本模块负责基于问题向量读写语义缓存，并封装缓存键、相似度查询和缓存统计。
它不负责决定何时使用缓存，也不负责聊天流程编排。
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import struct
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.config import config

logger = logging.getLogger("kagent.core.cache")


# ── Redis Index 名称 ────────────────────────────────────────────
_CACHE_PREFIX = "kagent:cache"
_EXACT_CACHE_PREFIX = "kagent:exact"


def _cache_index(namespace_version: str) -> str:
    return f"kagent:semantic_cache:{namespace_version}"


def _escape_tag_value(value: str) -> str:
    return re.sub(r"([^\w])", r"\\\1", value)


def _cache_scope(tenant_id: str, department: str) -> str:
    raw = json.dumps([tenant_id, department], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _vector_to_bytes(vector: List[float]) -> bytes:
    """将 float 列表编码为 float32 字节序列，用于 Redis VSS 存储。"""
    return struct.pack(f"{len(vector)}f", *vector)


def _bytes_to_vector(data: bytes) -> List[float]:
    """将 float32 字节序列解码为 float 列表。"""
    return list(struct.unpack(f"{len(data) // 4}f", data))


def _vector_key(
    tenant_id: str,
    vector: List[float],
    namespace_version: str = "v1",
    department: str = "general",
) -> str:
    """生成向量的确定性缓存键（用于精确匹配的非向量缓存路径）。"""
    vec_hash = hashlib.sha256(json.dumps(vector).encode()).hexdigest()[:16]
    return f"{_CACHE_PREFIX}:{namespace_version}:{_cache_scope(tenant_id, department)}:{vec_hash}"


def _tenant_namespace(tenant_id: str, namespace_version: str = "v1") -> str:
    """生成租户级命名空间键。"""
    return f"{_CACHE_PREFIX}:{namespace_version}:{tenant_id}"


def _exact_key(
    tenant_id: str,
    question_text: str,
    namespace_version: str = "v1",
    department: str = "general",
) -> str:
    normalized = " ".join(question_text.strip().lower().split())
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"{_EXACT_CACHE_PREFIX}:{namespace_version}:{_cache_scope(tenant_id, department)}:{digest}"


# ── Semantic Cache Manager ──────────────────────────────────────

@dataclass
class SemanticCacheManager:
    """Redis 向量语义缓存管理器。

    利用 RediSearch 的 Vector Similarity Search (VSS) 功能，
    在指定租户命名空间下进行 HNSW 余弦相似度检索。
    缓存失效策略：TTL 过期 + 语义漂移（相似度 < 阈值自动失效）。

    Fail-safe 设计：Redis 异常时自动降级跳过缓存，绝不阻塞主流程。
    """

    redis_url: str = field(default_factory=lambda: config.redis_url)
    ttl_seconds: int = field(default_factory=lambda: config.redis_cache_ttl_hours * 3600)
    similarity_threshold: float = field(default_factory=lambda: config.redis_cache_threshold)
    namespace_version: str = field(default_factory=lambda: config.cache_namespace_version)
    vector_dim: int = 768  # 向量维度（bge-base-zh-v1.5 输出 768 维）
    _client: Any = field(default=None, init=False, repr=False)
    _connected: bool = field(default=False, init=False, repr=False)
    _semantic_ready: bool = field(default=False, init=False, repr=False)

    @property
    def connected(self) -> bool:
        return self._connected and self._client is not None

    @property
    def semantic_ready(self) -> bool:
        return self.connected and self._semantic_ready

    async def connect(self) -> None:
        """建立 Redis 异步连接并创建 VSS 索引。"""
        try:
            import redis.asyncio as aioredis

            self._client = aioredis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True,
                retry_on_timeout=True,
            )
            # 验证连接
            await self._client.ping()

            self._connected = True
            self._semantic_ready = await self._ensure_index()
            logger.info(
                "Redis 缓存连接成功: %s (semantic_ready=%s)",
                self.redis_url,
                self._semantic_ready,
            )
        except ImportError:
            logger.warning("redis 库未安装，语义缓存不可用: pip install redis")
            self._connected = False
        except Exception as exc:
            logger.warning("Redis 连接失败，语义缓存降级: %s", exc)
            if self._client is not None:
                try:
                    await self._client.aclose()
                except Exception as close_exc:
                    logger.warning("Redis 失败连接关闭异常: %s", close_exc)
            self._connected = False
            self._semantic_ready = False
            self._client = None

    async def _ensure_index(self) -> bool:
        """确保 RediSearch 向量索引存在（幂等创建）。"""
        try:
            # 检查索引是否已存在
            await self._client.execute_command(
                "FT.INFO", _cache_index(self.namespace_version),
            )
            self._semantic_ready = True
            return True
        except Exception:
            # 索引不存在，创建
            try:
                await self._client.execute_command(
                    "FT.CREATE", _cache_index(self.namespace_version),
                    "ON", "HASH",
                    "PREFIX", "1", f"{_CACHE_PREFIX}:{self.namespace_version}:",
                    "SCHEMA",
                    "tenant_id", "TAG",
                    "question_text", "TEXT",
                    "answer", "TEXT",
                    "question_vector", "VECTOR", "HNSW",
                    "10",
                    "TYPE", "FLOAT32",
                    "DIM", str(self.vector_dim),
                    "DISTANCE_METRIC", "COSINE",
                    "M", "16",
                    "EF_CONSTRUCTION", "200",
                )
                self._semantic_ready = True
                logger.info("Redis VSS 索引创建成功: %s", _cache_index(self.namespace_version))
                return True
            except Exception as exc:
                logger.warning("Redis VSS 索引创建失败: %s", exc)
                self._semantic_ready = False
                return False

    async def close(self) -> None:
        """平滑关闭连接。"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            self._connected = False
            self._semantic_ready = False
            logger.info("Redis 缓存连接已关闭")

    # ── 语义检索缓存 ────────────────────────────────────────────

    async def get_cache(
        self,
        tenant_id: str,
        question_vector: List[float],
        department: str = "general",
    ) -> Optional[str]:
        """在指定租户命名空间下进行 VSS 语义检索。

        如果最高余弦相似度得分 > threshold，视为语义命中，返回缓存的 Answer。
        否则返回 None（cache miss）。

        Fail-safe: Redis 异常时返回 None，跳过缓存。
        """
        if not self.semantic_ready:
            return None
        if len(question_vector) != self.vector_dim:
            logger.warning(
                "Redis 语义缓存向量维度不匹配: expected=%d actual=%d",
                self.vector_dim,
                len(question_vector),
            )
            return None

        try:
            # RediSearch VECTOR相似度查询：KNN 检索最近邻
            # 在 tenant_id 命名空间内搜索，返回最相似的 1 条
            vector_bytes = _vector_to_bytes(question_vector)
            # TAG 过滤必须放在 query 内，FILTER 关键字不支持 TAG 语法
            tenant_tag = _escape_tag_value(_cache_scope(tenant_id, department))
            query = f"@tenant_id:{{{tenant_tag}}}=>[KNN 1 @question_vector $vector AS score]"

            result = await self._client.execute_command(
                "FT.SEARCH", _cache_index(self.namespace_version),
                query,
                "PARAMS", "2", "vector", vector_bytes,
                "RETURN", "2", "answer", "score",
                "DIALECT", "2",
                "LIMIT", "0", "1",
            )

            # 解析结果 — redis-py >= 8.0 返回 dict，旧版返回 list
            if isinstance(result, dict):
                total = result.get("total_results", 0)
                if total == 0:
                    logger.debug("Redis VSS miss: tenant=%s", tenant_id)
                    return None
                first = result["results"][0]
                fields_dict = first.get("extra_attributes", {})
            else:
                # 兼容旧版 list 格式: [count, doc_id, [field, val, ...]]
                if result[0] == 0:
                    logger.debug("Redis VSS miss: tenant=%s", tenant_id)
                    return None
                fields_raw = result[2]
                fields_dict = {fields_raw[i]: fields_raw[i + 1] for i in range(0, len(fields_raw), 2)}

            score = float(fields_dict.get("score", "0"))
            answer = fields_dict.get("answer", "")

            if score <= self.similarity_threshold and answer:
                logger.info(
                    "Redis 语义缓存命中: tenant=%s score=%.4f (threshold=%.2f)",
                    tenant_id, score, self.similarity_threshold,
                )
                return answer

            logger.debug(
                "Redis VSS score below threshold: %.4f < %.2f",
                score, self.similarity_threshold,
            )
            return None

        except Exception as exc:
            # Fail-safe: Redis 异常不影响主流程
            logger.warning("Redis 语义缓存检索异常，降级跳过: %s", exc)
            return None

    # ── 写入缓存 ────────────────────────────────────────────────

    async def set_cache(
        self,
        tenant_id: str,
        question_vector: List[float],
        answer: str,
        question_text: str = "",
        department: str = "general",
    ) -> bool:
        """将新问答对和向量写入 Redis，设置 TTL 超时时间。

        写入策略：
        - 使用租户命名空间前缀隔离
        - TTL = config.redis_cache_ttl_hours（默认 12 小时）
        - question_vector 存储为 FLOAT32 二进制用于 VSS

        Fail-safe: Redis 异常时返回 False，不影响主流程。
        """
        if not self.semantic_ready:
            return False
        if len(question_vector) != self.vector_dim:
            logger.warning(
                "Redis 语义缓存向量维度不匹配: expected=%d actual=%d",
                self.vector_dim,
                len(question_vector),
            )
            return False

        scope = _cache_scope(tenant_id, department)
        cache_key = _vector_key(
            tenant_id,
            question_vector,
            self.namespace_version,
            department,
        )

        try:
            # 构建 Hash 字段
            data = {
                "tenant_id": scope,
                "question_text": question_text[:500],
                "answer": answer,
                "question_vector": _vector_to_bytes(question_vector),
            }

            # Pipeline 写入 + 设置 TTL
            pipe = self._client.pipeline()
            pipe.hset(cache_key, mapping=data)
            pipe.expire(cache_key, self.ttl_seconds)
            await pipe.execute()

            logger.info(
                "Redis 缓存写入成功: tenant=%s key=%s ttl=%ds",
                tenant_id, cache_key[:40], self.ttl_seconds,
            )
            return True

        except Exception as exc:
            logger.warning("Redis 缓存写入异常: %s", exc)
            return False

    # ── 统计 ────────────────────────────────────────────────────

    async def get_exact_cache(
        self,
        tenant_id: str,
        question_text: str,
        department: str = "general",
    ) -> Optional[str]:
        """Return an exact question hit without computing an embedding."""
        if not self._connected or self._client is None:
            return None
        try:
            value = await self._client.get(
                _exact_key(tenant_id, question_text, self.namespace_version, department)
            )
            if isinstance(value, bytes):
                return value.decode("utf-8")
            return str(value) if value else None
        except Exception as exc:
            logger.warning("Redis exact cache lookup failed: %s", exc)
            return None

    async def set_exact_cache(
        self,
        tenant_id: str,
        question_text: str,
        answer: str,
        department: str = "general",
    ) -> bool:
        """Store an exact tenant-scoped cache entry."""
        if not self._connected or self._client is None:
            return False
        try:
            await self._client.set(
                _exact_key(tenant_id, question_text, self.namespace_version, department),
                answer,
                ex=self.ttl_seconds,
            )
            return True
        except Exception as exc:
            logger.warning("Redis exact cache write failed: %s", exc)
            return False

    async def stats(self) -> Dict[str, Any]:
        """返回缓存统计信息。"""
        if not self._connected or self._client is None:
            return {"connected": False, "cached_keys": 0}
        try:
            info = await self._client.execute_command("FT.INFO", _cache_index(self.namespace_version))
            return {
                "connected": True,
                "semantic_ready": self.semantic_ready,
                "namespace_version": self.namespace_version,
                "index_info": info[:10] if isinstance(info, list) else str(info)[:200],
            }
        except Exception:
            return {
                "connected": True,
                "semantic_ready": False,
                "namespace_version": self.namespace_version,
                "cached_keys": "unknown",
            }
