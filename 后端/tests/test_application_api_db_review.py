"""Application / API / DB 第二批审查缺陷回归测试。"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from src.api import routes
from src.api.auth import create_token, verify_token
from src.application.streaming_tasks import heartbeat_disconnect_monitor, race_with_heartbeat
from src.application import streaming_tasks
from src.application.rag_service import HybridRagService
from src.application.chat_flows import _schedule_cache_write
from src.application.orchestrator import ChatOrchestrator
from src.core.reranker import RerankResult
from src.core.router import ModelRouter
from src.core.schemas import GatewayWorkflowRequest
from src.config import GatewayConfig
from src.core.cache import SemanticCacheManager
from src.core.audit import sanitize_text
from src.core.prompts.registry import PromptRegistry
from src.db.bm25_client import SparseRetriever
from src.db.neo4j_client import GraphRepository
from src.db.qdrant_client import QdrantVectorStore


@pytest.mark.asyncio
async def test_exact_cache_key_is_isolated_by_department() -> None:
    cache = SemanticCacheManager()
    cache._client = AsyncMock()
    cache._connected = True
    cache._client.get.return_value = None

    await cache.get_exact_cache("tenant", "same question", department="hr")
    hr_key = cache._client.get.await_args.args[0]
    await cache.get_exact_cache("tenant", "same question", department="legal")
    legal_key = cache._client.get.await_args.args[0]

    assert hr_key != legal_key


def test_bm25_same_doc_id_cannot_cross_tenant_boundary() -> None:
    retriever = SparseRetriever()
    retriever.add_document(
        tenant_id="tenant-a",
        department="hr",
        doc_id="shared-id",
        text="alpha policy",
        metadata={"text": "tenant-a secret"},
    )
    retriever.add_document(
        tenant_id="tenant-b",
        department="hr",
        doc_id="shared-id",
        text="beta policy",
        metadata={"text": "tenant-b secret"},
    )

    results = retriever.search(
        tenant_id="tenant-a",
        department="hr",
        query="alpha",
    )

    assert results[0].metadata["tenant_id"] == "tenant-a"
    assert results[0].metadata["text"] == "tenant-a secret"


def test_bm25_score_is_not_affected_by_other_tenant_corpus() -> None:
    retriever = SparseRetriever()
    retriever.add_document(
        tenant_id="tenant-a",
        department="hr",
        doc_id="a",
        text="shared policy",
    )
    isolated_score = retriever.search(
        tenant_id="tenant-a", department="hr", query="shared"
    )[0].score
    retriever.add_document(
        tenant_id="tenant-b",
        department="hr",
        doc_id="b",
        text="shared policy",
    )
    score_after_other_tenant = retriever.search(
        tenant_id="tenant-a", department="hr", query="shared"
    )[0].score

    assert score_after_other_tenant == isolated_score


@pytest.mark.asyncio
async def test_qdrant_storage_id_is_namespaced_by_tenant_and_department() -> None:
    store = QdrantVectorStore()
    store._client = AsyncMock()

    await store.upsert_point(
        point_id="shared-id",
        vector=[0.1],
        payload={"tenant_id": "tenant-a", "department": "hr"},
    )
    first_id = store._client.upsert.await_args.kwargs["points"][0].id
    await store.upsert_point(
        point_id="shared-id",
        vector=[0.1],
        payload={"tenant_id": "tenant-b", "department": "hr"},
    )
    second_id = store._client.upsert.await_args.kwargs["points"][0].id

    assert first_id != second_id


@pytest.mark.asyncio
async def test_neo4j_uses_async_result_consume_for_summary() -> None:
    counters = SimpleNamespace(
        nodes_created=1,
        relationships_created=0,
        properties_set=1,
        labels_added=1,
    )
    summary = SimpleNamespace(
        counters=counters,
        result_available_after=2,
        result_consumed_after=3,
    )
    result = MagicMock()
    result.__aiter__.return_value = []
    result.consume = AsyncMock(return_value=summary)
    session = AsyncMock()
    session.run.return_value = result
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    driver = MagicMock()
    driver.session.return_value = session
    repo = GraphRepository()
    repo._driver = driver

    output = await repo.execute_cypher("RETURN 1")

    result.consume.assert_awaited_once()
    assert output.summary["counters"]["nodes_created"] == 1


@pytest.mark.asyncio
async def test_neo4j_tenant_entity_merge_includes_tenant_key() -> None:
    repo = GraphRepository()
    repo.execute_cypher = AsyncMock(return_value=SimpleNamespace())

    await repo.create_tenant_entity(
        tenant_id="tenant-a",
        label="Employee",
        properties={"name": "Alex"},
    )

    query = repo.execute_cypher.await_args.args[0]
    assert "{tenant_id: $tenant_id, name: $name}" in query
    with pytest.raises(ValueError):
        await repo.create_tenant_entity(
            tenant_id="tenant-a",
            label="Employee) MATCH (n) DETACH DELETE n //",
            properties={"name": "Alex"},
        )


@pytest.mark.asyncio
async def test_race_with_heartbeat_leaves_no_monitor_task() -> None:
    request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))
    before = set(asyncio.all_tasks())

    assert await race_with_heartbeat(request, asyncio.sleep(0, result="ok")) == "ok"
    await asyncio.sleep(0)
    leaked = [
        task
        for task in asyncio.all_tasks()
        if task not in before
        and not task.done()
        and getattr(task.get_coro(), "__qualname__", "")
        == heartbeat_disconnect_monitor.__qualname__
    ]

    for task in leaked:
        task.cancel()
    await asyncio.gather(*leaked, return_exceptions=True)
    assert leaked == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint",
    [routes.monitor_circuit_breaker_force_open, routes.monitor_circuit_breaker_force_close],
)
async def test_circuit_breaker_admin_endpoints_reject_jwt(endpoint) -> None:
    request = SimpleNamespace(state=SimpleNamespace(auth_method="jwt"))

    with pytest.raises(HTTPException) as exc_info:
        await endpoint(request)

    assert exc_info.value.status_code == 403


def test_production_config_rejects_default_jwt_secret() -> None:
    cfg = GatewayConfig()
    cfg.jwt_secret = "dev-secret-change-in-production!"
    cfg.debug = False
    cfg.allow_dev_tokens = False

    with pytest.raises(ValueError, match="JWT_SECRET"):
        cfg.validate_security()


def test_runtime_config_rejects_invalid_operational_ranges() -> None:
    cfg = GatewayConfig()
    cfg.redis_cache_ttl_hours = 0

    with pytest.raises(ValueError, match="REDIS_CACHE_TTL_HOURS"):
        cfg.validate_runtime()


def test_jwt_identity_is_normalized_and_scoped_to_issuer_audience() -> None:
    token = create_token(" user-a ", " tenant-a ", "hr")

    payload = verify_token(token)

    assert payload.user_id == "user-a"
    assert payload.tenant_id == "tenant-a"


@pytest.mark.asyncio
async def test_monitor_traces_scopes_jwt_to_current_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        routes.observer.metrics,
        "recent_traces",
        [
            {"trace_id": "mine", "tenant_id": "tenant-a", "user_id": "user-a"},
            {"trace_id": "other", "tenant_id": "tenant-b", "user_id": "user-b"},
        ],
    )
    request = SimpleNamespace(
        state=SimpleNamespace(
            auth_method="jwt",
            user=SimpleNamespace(user_id="user-a", tenant_id="tenant-a"),
        )
    )

    payload = await routes.monitor_traces(request=request, limit=100, offset=0)

    assert [trace["trace_id"] for trace in payload["traces"]] == ["mine"]


@pytest.mark.asyncio
async def test_rag_keeps_dense_results_when_sparse_search_fails() -> None:
    service = HybridRagService()
    service._dense_search = AsyncMock(return_value=[
        {"doc_id": "dense", "vector_score": 0.9, "metadata": {"text": "evidence"}}
    ])
    service._sparse_search = AsyncMock(side_effect=RuntimeError("bm25 down"))

    results, _ = await service.retrieve(
        query="policy",
        tenant_id="tenant",
        department="hr",
        top_k=3,
    )

    assert [result.doc_id for result in results] == ["dense"]


@pytest.mark.asyncio
async def test_rag_truncates_reranker_output_to_top_k() -> None:
    reranker = AsyncMock()
    reranker.rerank_documents.return_value = [
        RerankResult(doc_id=str(index), rerank_score=1.0, text=str(index), metadata={})
        for index in range(5)
    ]
    service = HybridRagService(reranker=reranker)
    service._dense_search = AsyncMock(return_value=[
        {"doc_id": "dense", "vector_score": 0.9, "metadata": {"text": "evidence"}}
    ])
    service._sparse_search = AsyncMock(return_value=[])

    results, _ = await service.retrieve(
        query="policy",
        tenant_id="tenant",
        department="hr",
        top_k=2,
    )

    assert len(results) == 2


@pytest.mark.asyncio
async def test_qdrant_connect_failure_closes_created_client(monkeypatch: pytest.MonkeyPatch) -> None:
    client = AsyncMock()
    client.get_collections.side_effect = RuntimeError("down")
    monkeypatch.setattr("src.db.qdrant_client.AsyncQdrantClient", MagicMock(return_value=client))
    store = QdrantVectorStore()

    with pytest.raises(RuntimeError):
        await store.connect()

    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_neo4j_connect_failure_closes_created_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    driver = AsyncMock()
    driver.verify_connectivity.side_effect = RuntimeError("down")
    monkeypatch.setattr(
        "src.db.neo4j_client.AsyncGraphDatabase.driver",
        MagicMock(return_value=driver),
    )
    repo = GraphRepository()

    with pytest.raises(RuntimeError):
        await repo.connect()

    driver.close.assert_awaited_once()


@pytest.mark.parametrize(
    "secret_text",
    [
        "postgresql://admin:supersecret@db.local/app",
        "eyJhbGciOiJIUzI1NiJ9.abc.signature",
        "Cookie: sessionid=topsecret",
    ],
)
def test_audit_sanitizes_common_embedded_credentials(secret_text: str) -> None:
    sanitized = sanitize_text(secret_text)

    assert "supersecret" not in sanitized
    assert "eyJhbGciOiJIUzI1NiJ9.abc.signature" not in sanitized
    assert "topsecret" not in sanitized


def test_prompt_directory_load_is_atomic_on_invalid_entry(tmp_path) -> None:
    (tmp_path / "valid.txt").write_text("Hello {name}", encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "prompts": [
                    {"name": "valid", "version": "1.0.0", "file": "valid.txt"},
                    {"name": "missing", "version": "1.0.0", "file": "missing.txt"},
                ]
            }
        ),
        encoding="utf-8",
    )
    registry = PromptRegistry()

    with pytest.raises(FileNotFoundError):
        registry.load_directory(tmp_path)

    assert registry.list() == []


@pytest.mark.asyncio
async def test_workflow_api_enforces_total_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    class SlowEngine:
        async def run(self, *_: object, **__: object) -> object:
            await asyncio.sleep(1)
            return SimpleNamespace()

    monkeypatch.setattr(routes.config, "workflow_timeout_seconds", 0.01, raising=False)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(workflow_engine=SlowEngine())),
        state=SimpleNamespace(
            user=SimpleNamespace(user_id="user", tenant_id="tenant", department="hr")
        )
    )
    body = GatewayWorkflowRequest(
        user_id="ignored",
        tenant_id="ignored",
        question="question",
        workflow_name="research",
    )

    with pytest.raises(HTTPException) as exc_info:
        await routes.gateway_workflow(body, request)

    assert exc_info.value.status_code == 504


@pytest.mark.asyncio
async def test_orchestrator_drains_background_cache_tasks() -> None:
    async def complete_write(**_: object) -> bool:
        await asyncio.sleep(0)
        return True

    cache = AsyncMock()
    cache.set_exact_cache.side_effect = complete_write
    cache.set_cache.side_effect = complete_write
    orchestrator = ChatOrchestrator(
        model_router=ModelRouter(),
        agent_runtime=AsyncMock(),
        semantic_cache=cache,
    )
    request = SimpleNamespace(
        tenant_id="tenant",
        department="hr",
        question="question",
    )

    _schedule_cache_write(orchestrator, request, "answer", [0.1])
    assert orchestrator.background_tasks
    await orchestrator.drain_background_tasks()

    assert orchestrator.background_tasks == set()


def test_streaming_tasks_has_no_module_global_provider_factory() -> None:
    assert not hasattr(streaming_tasks, "provider_factory")


@pytest.mark.asyncio
async def test_gateway_workflow_uses_app_state_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    result = SimpleNamespace(
        workflow_name="research",
        mode=SimpleNamespace(value="sequential"),
        status="completed",
        final_answer="answer",
        steps=[],
        total_duration_ms=1.0,
        total_tokens=1,
    )
    app_engine = AsyncMock()
    app_engine.run.return_value = result
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(workflow_engine=app_engine)),
        state=SimpleNamespace(
            user=SimpleNamespace(user_id="user", tenant_id="tenant", department="hr")
        ),
    )
    body = GatewayWorkflowRequest(
        user_id="ignored",
        tenant_id="ignored",
        question="question",
        workflow_name="research",
    )

    response = await routes.gateway_workflow(body, request)

    assert response.final_answer == "answer"
    app_engine.run.assert_awaited_once()
