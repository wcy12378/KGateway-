"""Neo4j 图数据库适配客户端。

本模块负责封装 Neo4j 异步连接、查询执行和连接生命周期。它不负责业务编排、
RAG 决策或前端数据展示。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from neo4j import AsyncDriver, AsyncGraphDatabase, Record

logger = logging.getLogger("kagent.db.neo4j")
_LABEL_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


# ── Cypher 查询结果 ─────────────────────────────────────────────

@dataclass
class CypherResult:
    """Cypher 查询执行结果。"""

    records: List[Dict[str, Any]]
    summary: Dict[str, Any]


# ── 图数据库仓库 ────────────────────────────────────────────────

@dataclass
class GraphRepository:
    """Neo4j 异步图数据库仓库。

    封装连接池管理，提供 Cypher 执行能力，
    支持多租户图谱查询与知识图谱构建。
    """

    uri: str = field(default="bolt://localhost:7687")
    user: str = field(default="neo4j")
    password: str = field(default="")
    max_connection_pool_size: int = field(default=50)
    connection_timeout: float = field(default=30.0)
    _driver: Optional[AsyncDriver] = field(default=None, init=False, repr=False)

    async def connect(self) -> None:
        """创建异步驱动并建立连接池。"""
        try:
            self._driver = AsyncGraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password),
                max_connection_pool_size=self.max_connection_pool_size,
                connection_timeout=self.connection_timeout,
            )
            # 验证连接
            await self._driver.verify_connectivity()
            logger.info("Neo4j 连接成功: %s", self.uri)
        except Exception as exc:
            logger.error("Neo4j 连接失败: %s", exc)
            driver = self._driver
            self._driver = None
            if driver is not None:
                try:
                    await driver.close()
                except Exception as close_exc:
                    logger.warning("Neo4j 失败连接关闭异常: %s", close_exc)
            raise

    async def close(self) -> None:
        """平滑关闭连接池。"""
        if self._driver is not None:
            await self._driver.close()
            self._driver = None
            logger.info("Neo4j 连接池已关闭")

    @property
    def driver(self) -> AsyncDriver:
        if self._driver is None:
            raise RuntimeError("Neo4j 未连接，请先调用 connect()")
        return self._driver

    # ── Cypher 执行 ─────────────────────────────────────────────

    async def execute_cypher(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> CypherResult:
        """执行 Cypher 查询并返回结果。

        Args:
            query: Cypher 查询语句。
            parameters: 查询参数（推荐使用参数化查询防止注入）。

        Returns:
            CypherResult 包含 records 和 summary。
        """
        if not query.strip():
            raise ValueError("Cypher 查询不能为空")

        try:
            async with self.driver.session() as session:
                result = await session.run(query, parameters or {})
                records = []
                async for record in result:
                    records.append(dict(record))
                result_summary = await result.consume()
                summary = {
                    "counters": {
                        "nodes_created": result_summary.counters.nodes_created,
                        "relationships_created": result_summary.counters.relationships_created,
                        "properties_set": result_summary.counters.properties_set,
                        "labels_added": result_summary.counters.labels_added,
                    },
                    "result_available_after": result_summary.result_available_after,
                    "result_consumed_after": result_summary.result_consumed_after,
                }
        except Exception as exc:
            logger.error("Cypher 执行失败: query=%s err=%s", query[:100], exc)
            raise

        logger.info(
            "Cypher 执行完成: records=%d query=%s",
            len(records),
            query[:80],
        )
        return CypherResult(records=records, summary=summary)

    # ── 多租户图谱查询 ──────────────────────────────────────────

    async def query_tenant_graph(
        self,
        *,
        tenant_id: str,
        label: Optional[str] = None,
        limit: int = 100,
    ) -> CypherResult:
        """查询指定租户的图谱节点。

        通过 WHERE t.tenant_id = $tenant_id 硬过滤，确保跨租户数据隔离。
        """
        if label is not None and not _LABEL_PATTERN.fullmatch(label):
            raise ValueError("Neo4j label 格式无效")
        label_clause = f":{label}" if label else ""
        query = f"""
            MATCH (n{label_clause})-[:BELONGS_TO]->(t:Tenant)
            WHERE t.tenant_id = $tenant_id
            RETURN n, t.tenant_id AS tenant_id
            LIMIT $limit
        """
        return await self.execute_cypher(query, {"tenant_id": tenant_id, "limit": limit})

    async def create_tenant_entity(
        self,
        *,
        tenant_id: str,
        label: str,
        properties: Dict[str, Any],
    ) -> CypherResult:
        """在租户下创建实体节点。"""
        if not _LABEL_PATTERN.fullmatch(label):
            raise ValueError("Neo4j label 格式无效")
        scoped_properties = dict(properties)
        scoped_properties["tenant_id"] = tenant_id
        query = f"""
            MERGE (t:Tenant {{tenant_id: $tenant_id}})
            MERGE (n:{label} {{tenant_id: $tenant_id, name: $name}})
            SET n += $properties
            MERGE (n)-[:BELONGS_TO]->(t)
            RETURN n
        """
        params = {
            "tenant_id": tenant_id,
            "name": scoped_properties.get("name", ""),
            "properties": scoped_properties,
        }
        return await self.execute_cypher(query, params)
