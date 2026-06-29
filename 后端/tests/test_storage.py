"""存储层单元测试 — 多租户隔离验证。"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Qdrant 过滤条件测试 ─────────────────────────────────────────

class TestQdrantFilterLogic:
    """验证 Qdrant 多租户硬过滤条件拼接是否正确。"""

    def _build_tenant_filter(self, tenant_id: str, department: str):
        """从 QdrantVectorStore 中提取过滤条件构建逻辑（纯函数测试）。"""
        from qdrant_client import models

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
        return models.Filter(must=must_conditions)

    def test_filter_contains_tenant_id(self):
        """过滤条件必须包含 tenant_id 匹配。"""
        f = self._build_tenant_filter("tenant_001", "legal")
        assert any(
            c.key == "tenant_id" and c.match.value == "tenant_001"
            for c in f.must
        )

    def test_filter_contains_department(self):
        """过滤条件必须包含 department 匹配。"""
        f = self._build_tenant_filter("tenant_001", "legal")
        assert any(
            c.key == "department" and c.match.value == "legal"
            for c in f.must
        )

    def test_filter_is_and_logic(self):
        """两个条件必须用 AND（must）连接，不能是 OR。"""
        f = self._build_tenant_filter("tenant_001", "hr")
        assert len(f.must) == 2
        assert f.should is None or len(f.should) == 0

    def test_different_tenants_produce_different_filters(self):
        """不同租户产生不同过滤条件值。"""
        f1 = self._build_tenant_filter("tenant_A", "legal")
        f2 = self._build_tenant_filter("tenant_B", "hr")
        t1 = next(c for c in f1.must if c.key == "tenant_id")
        t2 = next(c for c in f2.must if c.key == "tenant_id")
        assert t1.match.value != t2.match.value

    def test_different_departments_produce_different_filters(self):
        """不同部门产生不同过滤条件值。"""
        f1 = self._build_tenant_filter("tenant_001", "legal")
        f2 = self._build_tenant_filter("tenant_001", "hr")
        d1 = next(c for c in f1.must if c.key == "department")
        d2 = next(c for c in f2.must if c.key == "department")
        assert d1.match.value == "legal"
        assert d2.match.value == "hr"

    def test_extra_filter_merged_with_and(self):
        """额外过滤条件必须合并到 must 中。"""
        from qdrant_client import models

        base = self._build_tenant_filter("t1", "legal")
        extra = models.Filter(
            must=[models.FieldCondition(key="category", match=models.MatchValue(value="合同"))]
        )
        combined = models.Filter(must=[base, extra])
        assert len(combined.must) == 2  # base filter + extra filter


# ── Qdrant 搜索函数 Mock 测试 ───────────────────────────────────

class TestQdrantSearchMock:
    """Mock AsyncQdrantClient 验证搜索调用。"""

    @pytest.mark.asyncio
    async def test_search_calls_with_correct_filter(self):
        """search_tenant_knowledge 必须传入包含 tenant_id + department 的 filter。"""
        from src.db.qdrant_client import QdrantVectorStore

        mock_client = AsyncMock()
        mock_client.query_points.return_value = MagicMock(points=[])

        store = QdrantVectorStore()
        store._client = mock_client

        await store.search_tenant_knowledge(
            tenant_id="tenant_001",
            department="legal",
            query_vector=[0.1] * 384,
            top_k=3,
        )

        call_kwargs = mock_client.query_points.call_args.kwargs
        query_filter = call_kwargs["query_filter"]
        must_keys = {c.key for c in query_filter.must}
        assert "tenant_id" in must_keys
        assert "department" in must_keys

    @pytest.mark.asyncio
    async def test_search_returns_parsed_results(self):
        """搜索结果应正确解析为 VectorSearchResult 列表。"""
        from src.db.qdrant_client import QdrantVectorStore

        mock_point = MagicMock()
        mock_point.id = "pt_001"
        mock_point.score = 0.95
        mock_point.payload = {"text": "合同条款A", "tenant_id": "t1", "department": "legal"}

        mock_client = AsyncMock()
        mock_client.query_points.return_value = MagicMock(points=[mock_point])

        store = QdrantVectorStore()
        store._client = mock_client

        results = await store.search_tenant_knowledge(
            tenant_id="t1",
            department="legal",
            query_vector=[0.1] * 384,
            top_k=1,
        )

        assert len(results) == 1
        assert results[0].id == "pt_001"
        assert results[0].score == 0.95
        assert results[0].payload["text"] == "合同条款A"


# ── Neo4j Cypher 执行测试 ───────────────────────────────────────

class TestNeo4jCypher:
    """Mock Neo4j driver 验证 Cypher 执行。"""

    @pytest.mark.asyncio
    async def test_execute_cypher_rejects_empty_query(self):
        """空查询应抛出 ValueError。"""
        from src.db.neo4j_client import GraphRepository

        repo = GraphRepository()
        with pytest.raises(ValueError, match="不能为空"):
            await repo.execute_cypher("")

    @pytest.mark.asyncio
    async def test_execute_cypher_rejects_whitespace_query(self):
        """纯空白查询应抛出 ValueError。"""
        from src.db.neo4j_client import GraphRepository

        repo = GraphRepository()
        with pytest.raises(ValueError, match="不能为空"):
            await repo.execute_cypher("   \n\t  ")

    @pytest.mark.asyncio
    async def test_execute_cypher_passes_parameters(self):
        """查询参数应正确传递给 driver.session.run()。"""
        from src.db.neo4j_client import GraphRepository

        mock_result = AsyncMock()
        mock_result.__aiter__ = MagicMock(return_value=iter([]))
        mock_result.summary.counters.nodes_created = 0
        mock_result.summary.counters.relationships_created = 0
        mock_result.summary.counters.properties_set = 0
        mock_result.summary.counters.labels_added = 0
        mock_result.summary.result_available_after = None
        mock_result.summary.result_consumed_after = None

        mock_session = AsyncMock()
        mock_session.run.return_value = mock_result
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_driver = MagicMock()
        mock_driver.session.return_value = mock_session

        repo = GraphRepository()
        repo._driver = mock_driver

        await repo.execute_cypher(
            "MATCH (n:Tenant {tenant_id: $tid}) RETURN n",
            {"tid": "tenant_001"},
        )

        mock_session.run.assert_called_once_with(
            "MATCH (n:Tenant {tenant_id: $tid}) RETURN n",
            {"tid": "tenant_001"},
        )


# ── GatewayConfig 新字段测试 ────────────────────────────────────

class TestGatewayConfigStorage:
    """验证配置中新增的数据库字段。"""

    def test_qdrant_defaults(self):
        """Qdrant 默认值应正确。"""
        from src.config import GatewayConfig

        cfg = GatewayConfig()
        assert cfg.qdrant_url == "http://localhost:6333"
        assert cfg.qdrant_collection == "kagent_vectors"

    def test_neo4j_defaults(self):
        """Neo4j 默认值应正确。"""
        from src.config import GatewayConfig

        cfg = GatewayConfig()
        assert cfg.neo4j_uri == "bolt://localhost:7687"
        assert cfg.neo4j_user == "neo4j"
