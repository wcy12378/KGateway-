"""KAgent FastAPI 应用入口。

本模块负责创建 FastAPI 应用、初始化运行时依赖并挂载 API 路由。它不直接
实现聊天编排、检索算法或前端页面逻辑。
"""

from __future__ import annotations

import logging
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("kagent.main")

_src_dir = Path(__file__).resolve().parent
if str(_src_dir.parent) not in sys.path:
    sys.path.insert(0, str(_src_dir.parent))

from src.agents.runtime import AgentRuntime  # noqa: E402
from src.api.auth import PUBLIC_PATHS, verify_token  # noqa: E402
from src.api.routes import build_metrics_payload  # noqa: E402
from src.api.routes import init_router  # noqa: E402
from src.api.routes import monitor_router  # noqa: E402
from src.api.routes import router as gateway_router  # noqa: E402
from src.api.token_routes import router as token_router  # noqa: E402
from src.config import config  # noqa: E402
from src.core.cache import SemanticCacheManager  # noqa: E402
import src.core.tools.builtin  # noqa: E402, F401
from src.core.mcp.server_registry import get_mcp_registry  # noqa: E402
from src.core.observability import observer  # noqa: E402
from src.core.protection import CircuitBreaker  # noqa: E402
from src.core.providers.factory import ProviderFactory  # noqa: E402
from src.core.reranker import Reranker  # noqa: E402
from src.core.router import ModelRouter  # noqa: E402
from src.db.bm25_client import SparseRetriever  # noqa: E402
from src.db.neo4j_client import GraphRepository  # noqa: E402
from src.db.qdrant_client import QdrantVectorStore  # noqa: E402

_start_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    router = ModelRouter()

    bm25 = SparseRetriever()
    logger.info("BM25 sparse retriever initialized")

    reranker: Reranker | None = Reranker()
    try:
        await reranker.load_model()
    except Exception:
        logger.warning("Reranker model load failed, precision rerank disabled")
        reranker = None

    semantic_cache = SemanticCacheManager()
    try:
        await semantic_cache.connect()
    except Exception:
        logger.warning("Redis semantic cache connection failed")

    provider_factory = ProviderFactory()
    provider_factory.init(config)
    app.state.provider_factory = provider_factory
    logger.info("LLM Provider 工厂已初始化，默认 Provider: %s", config.kagent_llm_provider)

    agent_runtime = AgentRuntime(
        provider_factory=provider_factory,
        max_iterations=4,
        timeout_seconds=60.0,
        rag_pipeline_fn=None,
    )
    logger.info("AgentRuntime initialized")

    mcp_registry = get_mcp_registry()
    if config.mcp_servers:
        for server_config in config.mcp_servers.split(";"):
            server_config = server_config.strip()
            if not server_config:
                continue
            parts = server_config.split(":", 2)
            if len(parts) < 2 or not parts[0].strip() or not parts[1].strip():
                logger.warning("MCP Server 配置无效，已跳过: %s", server_config)
                continue
            name = parts[0].strip()
            command = parts[1].strip()
            args = [item for item in parts[2].split("|") if item] if len(parts) > 2 else []
            try:
                await mcp_registry.register_server(name, command, args)
            except Exception as exc:
                logger.warning("MCP Server '%s' 初始化失败: %s", name, exc)
    app.state.mcp_registry = mcp_registry

    circuit_breaker = CircuitBreaker(
        name="llm_api",
        failure_threshold=config.circuit_breaker_threshold,
        recovery_timeout=config.circuit_breaker_timeout,
    )
    logger.info(
        "Circuit breaker initialized threshold=%d timeout=%ds",
        config.circuit_breaker_threshold,
        config.circuit_breaker_timeout,
    )

    qdrant_store = QdrantVectorStore(
        url=config.qdrant_url,
        api_key=config.qdrant_api_key,
        collection=config.qdrant_collection,
    )
    try:
        await qdrant_store.connect()
    except Exception:
        logger.warning("Qdrant connection failed")

    await observer.init_langfuse()

    init_router(
        router,
        bm25_retriever=bm25,
        reranker=reranker,
        agent_runtime=agent_runtime,
        semantic_cache=semantic_cache,
        circuit_breaker=circuit_breaker,
        qdrant_store=qdrant_store,
    )

    graph_repo = GraphRepository(
        uri=config.neo4j_uri,
        user=config.neo4j_user,
        password=config.neo4j_password,
    )
    try:
        await graph_repo.connect()
    except Exception:
        logger.warning("Neo4j connection failed")

    app.state.qdrant_store = qdrant_store
    app.state.graph_repo = graph_repo
    app.state.bm25_retriever = bm25
    app.state.reranker = reranker
    app.state.agent_runtime = agent_runtime
    app.state.semantic_cache = semantic_cache
    app.state.circuit_breaker = circuit_breaker

    logger.info("KAgent initialized and ready on POST /api/v1/gateway/stream")

    yield

    await mcp_registry.close_all()
    await router.print_session_summary()
    await semantic_cache.close()
    await qdrant_store.close()
    await graph_repo.close()
    logger.info("KAgent shutdown complete")


app = FastAPI(
    title="KAgent",
    description="Enterprise LLM gateway with unified routing and cost control",
    version="0.3.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """全局验证 Bearer token，并把身份写入 request.state。"""
    path = request.url.path
    if path in PUBLIC_PATHS:
        return await call_next(request)

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer ") or not auth_header[7:].strip():
        return JSONResponse(
            status_code=401,
            content={"detail": "缺少认证信息，请在请求头中添加 Authorization: Bearer <token>"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        request.state.user = verify_token(auth_header[7:].strip())
    except HTTPException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await call_next(request)


app.include_router(token_router)
app.include_router(gateway_router)
app.include_router(monitor_router)


@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/gateway/metrics", tags=["observability"])
async def gateway_metrics() -> dict:
    metrics = build_metrics_payload()
    cb_stats = app.state.circuit_breaker.stats() if hasattr(app.state, "circuit_breaker") else {}
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - _start_time, 0),
        "metrics": metrics,
        "circuit_breaker": cb_stats,
    }


if __name__ == "__main__":
    try:
        import uvicorn
    except ImportError:
        logger.error("Please install uvicorn")
        sys.exit(1)

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
