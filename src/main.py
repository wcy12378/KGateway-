"""KGateway FastAPI 入口。"""

from __future__ import annotations

import logging
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI

# ── 日志配置 ─────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("kgateway.main")

# ── 确保 src 可被导入 ───────────────────────────────────────────
_src_dir = Path(__file__).resolve().parent
if str(_src_dir.parent) not in sys.path:
    sys.path.insert(0, str(_src_dir.parent))


# ── Lifespan：启动时初始化全部组件 ─────────────────────────────
from src.agents.runtime import AgentRuntime  # noqa: E402
from src.api.routes import _rag_pipeline  # noqa: E402
from src.api.routes import init_router  # noqa: E402
from src.config import config  # noqa: E402
from src.core.cache import SemanticCacheManager  # noqa: E402
from src.core.observability import observer  # noqa: E402
from src.core.protection import CircuitBreaker  # noqa: E402
from src.core.reranker import Reranker  # noqa: E402
from src.core.router import ModelRouter  # noqa: E402
from src.db.bm25_client import SparseRetriever  # noqa: E402
from src.db.qdrant_client import QdrantVectorStore  # noqa: E402
from src.db.neo4j_client import GraphRepository  # noqa: E402

_start_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期管理：启动 → 初始化全部组件 → 关闭 → 释放资源。"""
    # ── 初始化路由器 ──
    router = ModelRouter()

    # ── 初始化 BM25 稀疏检索器 ──
    bm25 = SparseRetriever()
    logger.info("BM25 稀疏检索器已初始化")

    # ── 初始化 Reranker 精排模型 ──
    reranker = Reranker()
    try:
        await reranker.load_model()
    except Exception:
        logger.warning("Reranker 模型加载失败，精排功能降级")

    # ── 初始化 Agent Runtime ──
    agent_runtime = AgentRuntime(
        max_iterations=4,
        timeout_seconds=60.0,
        rag_pipeline_fn=_rag_pipeline,
    )
    logger.info("Agent Runtime 已初始化: max_iterations=4, timeout=60s")

    # ── 初始化 Redis 语义缓存 ──
    semantic_cache = SemanticCacheManager()
    try:
        await semantic_cache.connect()
    except Exception:
        logger.warning("Redis 语义缓存连接失败，缓存功能降级")

    # ── 初始化熔断器 ──
    circuit_breaker = CircuitBreaker(
        name="llm_api",
        failure_threshold=config.circuit_breaker_threshold,
        recovery_timeout=config.circuit_breaker_timeout,
    )
    logger.info(
        "熔断器已初始化: threshold=%d, recovery=%ds",
        config.circuit_breaker_threshold, config.circuit_breaker_timeout,
    )

    # ── 初始化可观测性 ──
    await observer.init_langfuse()

    # ── 注入所有组件 ──
    init_router(
        router,
        bm25_retriever=bm25,
        reranker=reranker,
        agent_runtime=agent_runtime,
        semantic_cache=semantic_cache,
        circuit_breaker=circuit_breaker,
    )

    # ── 初始化 Qdrant 连接池 ──
    qdrant_store = QdrantVectorStore(
        url=config.qdrant_url,
        api_key=config.qdrant_api_key,
        collection=config.qdrant_collection,
    )
    try:
        await qdrant_store.connect()
    except Exception:
        logger.warning("Qdrant 连接失败，向量检索功能不可用")

    # ── 初始化 Neo4j 连接池 ──
    graph_repo = GraphRepository(
        uri=config.neo4j_uri,
        user=config.neo4j_user,
        password=config.neo4j_password,
    )
    try:
        await graph_repo.connect()
    except Exception:
        logger.warning("Neo4j 连接失败，图谱查询功能不可用")

    # 挂载到 app.state
    app.state.qdrant_store = qdrant_store
    app.state.graph_repo = graph_repo
    app.state.bm25_retriever = bm25
    app.state.reranker = reranker
    app.state.agent_runtime = agent_runtime
    app.state.semantic_cache = semantic_cache
    app.state.circuit_breaker = circuit_breaker

    logger.info("KGateway 全部组件已初始化（含缓存+熔断），等待请求...")
    print("[KGateway] 网关已启动，端点: POST /api/v1/gateway/stream")

    yield

    # ── 关闭：平滑释放所有连接池 ──
    await router.print_session_summary()
    await semantic_cache.close()
    await qdrant_store.close()
    await graph_repo.close()
    logger.info("KGateway 已关闭，所有连接池已释放")


# ── FastAPI 实例 ─────────────────────────────────────────────────
app = FastAPI(
    title="KGateway",
    description="企业级智能网关 — 统一 LLM 路由与成本管控",
    version="0.2.0",
    lifespan=lifespan,
)

# ── 挂载路由 ─────────────────────────────────────────────────────
from src.api.routes import router as gateway_router  # noqa: E402

app.include_router(gateway_router)


# ── 健康检查 ─────────────────────────────────────────────────────
@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


# ── 实时监控指标端点 ─────────────────────────────────────────────
@app.get("/api/v1/gateway/metrics", tags=["observability"])
async def gateway_metrics() -> dict:
    """对外暴露实时健康指标（JSON 格式）。

    返回：总 Token 花费、缓存命中率、熔断器状态、延迟分布。
    """
    metrics = observer.metrics.snapshot()
    cb_stats = app.state.circuit_breaker.stats() if hasattr(app.state, "circuit_breaker") else {}
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - _start_time, 0),
        "metrics": metrics,
        "circuit_breaker": cb_stats,
    }


# ── Uvicorn 启动入口 ─────────────────────────────────────────────
if __name__ == "__main__":
    try:
        import uvicorn
    except ImportError:
        logger.error("请安装 uvicorn: pip install uvicorn")
        sys.exit(1)

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
