"""KAgent FastAPI 应用入口。

本模块负责创建 FastAPI 应用、初始化运行时依赖并挂载 API 路由。它不直接
实现聊天编排、检索算法或前端页面逻辑。
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

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
from src.api.auth import PUBLIC_PATHS, verify_api_key_value, verify_token  # noqa: E402
from src.api.routes import build_metrics_payload  # noqa: E402
from src.api.routes import init_router  # noqa: E402
from src.api.routes import monitor_router  # noqa: E402
from src.api.routes import router as gateway_router  # noqa: E402
from src.api.token_routes import router as token_router  # noqa: E402
from src.application.fast_lane import FastLaneService  # noqa: E402
from src.config import config  # noqa: E402
from src.core.agent.memory import MemoryManager  # noqa: E402
from src.core.agent.workflow import (  # noqa: E402
    AgentSpec,
    RoutingRule,
    WorkflowEngine,
    WorkflowMode,
)
from src.core.audit import AuditLogger  # noqa: E402
from src.core.cache import SemanticCacheManager  # noqa: E402
from src.core.embedder import warmup_embedding  # noqa: E402
import src.core.tools.builtin  # noqa: E402, F401
from src.core.mcp.server_registry import get_mcp_registry  # noqa: E402
from src.core.observability import observer  # noqa: E402
from src.core.protection import CircuitBreaker  # noqa: E402
from src.core.prompts.registry import PromptRegistry, get_registry as get_prompt_registry  # noqa: E402
from src.core.providers.factory import ProviderFactory  # noqa: E402
from src.core.reranker import Reranker  # noqa: E402
from src.core.router import ModelRouter  # noqa: E402
from src.db.bm25_client import SparseRetriever  # noqa: E402
from src.db.neo4j_client import GraphRepository  # noqa: E402
from src.db.qdrant_client import QdrantVectorStore  # noqa: E402

_start_time = time.time()


def _build_workflow_engine(
    provider_factory: ProviderFactory,
    memory_manager: MemoryManager,
    prompt_registry: PromptRegistry,
    audit_logger: AuditLogger,
) -> WorkflowEngine:
    engine = WorkflowEngine(
        provider_factory,
        memory_manager=memory_manager,
        prompt_registry=prompt_registry,
        audit_logger=audit_logger,
        max_parallelism=4,
    )

    engine.register_workflow(
        name="research",
        mode=WorkflowMode.SEQUENTIAL,
        agents=(
            AgentSpec(
                name="knowledge_retriever",
                description="检索企业知识并提炼证据",
                prompt_name="research_retriever",
                tool_names=("query_knowledge",),
                max_iterations=3,
            ),
            AgentSpec(
                name="research_writer",
                description="基于检索证据生成最终回答",
                prompt_name="research_writer",
                max_iterations=2,
            ),
        ),
    )

    engine.register_workflow(
        name="smart_route",
        mode=WorkflowMode.ROUTING,
        agents=(
            AgentSpec(
                name="enterprise_specialist",
                description="处理企业制度和内部知识问题",
                prompt_name="enterprise_specialist",
                tool_names=("query_knowledge",),
                max_iterations=3,
            ),
            AgentSpec(
                name="math_specialist",
                description="处理计算和数值问题",
                prompt_name="math_specialist",
                tool_names=("calculator",),
                max_iterations=3,
            ),
            AgentSpec(
                name="general_specialist",
                description="处理不属于专门领域的一般问题",
                prompt_name="general_specialist",
                max_iterations=2,
            ),
        ),
        routing_rules=(
            RoutingRule(
                agent_name="math_specialist",
                keywords=("计算", "算一下", "数学", "加", "减", "乘", "除", "+", "*", "/"),
            ),
            RoutingRule(
                agent_name="enterprise_specialist",
                keywords=("公司", "制度", "流程", "规定", "内部", "知识库", "报销", "请假"),
            ),
        ),
        fallback_agent="general_specialist",
    )

    engine.register_workflow(
        name="multi_review",
        mode=WorkflowMode.PARALLEL,
        agents=(
            AgentSpec(
                name="solution_analyst",
                description="从可行性和执行路径分析问题",
                prompt_name="solution_analyst",
                max_iterations=2,
            ),
            AgentSpec(
                name="risk_reviewer",
                description="独立识别风险、遗漏和反例",
                prompt_name="risk_reviewer",
                max_iterations=2,
            ),
        ),
        synthesizer=AgentSpec(
            name="review_synthesizer",
            description="合并多方分析形成最终结论",
            prompt_name="review_synthesizer",
            max_iterations=2,
        ),
    )
    return engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    config.validate_security()
    config.validate_runtime()
    router = ModelRouter()

    if config.embedding_warmup_enabled:
        dimension = await asyncio.to_thread(warmup_embedding, config.embedding_model_name)
        logger.info("Embedding warmup complete: model=%s dimension=%d", config.embedding_model_name, dimension)

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
    faq_path = config.faq_path if config.faq_path.is_absolute() else config.project_root / config.faq_path
    fast_lane = FastLaneService(faq_path=faq_path)

    provider_factory = ProviderFactory()
    provider_factory.init(config)
    app.state.provider_factory = provider_factory
    logger.info("LLM Provider 工厂已初始化，默认 Provider: %s", config.kagent_llm_provider)

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

    memory_manager = MemoryManager(
        qdrant_store=qdrant_store if qdrant_store.connected else None,
    )
    prompt_registry = get_prompt_registry()
    audit_logger = AuditLogger(max_entries=config.audit_max_entries)
    agent_runtime = AgentRuntime(
        provider_factory=provider_factory,
        max_iterations=4,
        timeout_seconds=60.0,
        rag_pipeline_fn=None,
        memory_manager=memory_manager,
        prompt_registry=prompt_registry,
        audit_logger=audit_logger,
    )
    workflow_engine = _build_workflow_engine(
        provider_factory,
        memory_manager,
        prompt_registry,
        audit_logger,
    )
    logger.info(
        "AgentRuntime initialized, long-term memory=%s",
        "enabled" if qdrant_store.connected else "degraded",
    )

    await observer.init_langfuse()

    chat_orchestrator = init_router(
        router,
        bm25_retriever=bm25,
        reranker=reranker,
        agent_runtime=agent_runtime,
        semantic_cache=semantic_cache,
        circuit_breaker=circuit_breaker,
        qdrant_store=qdrant_store,
        workflow_engine=workflow_engine,
        prompt_registry=prompt_registry,
        provider_factory=provider_factory,
        fast_lane=fast_lane,
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
    app.state.memory_manager = memory_manager
    app.state.workflow_engine = workflow_engine
    app.state.prompt_registry = prompt_registry
    app.state.audit_logger = audit_logger
    app.state.graph_repo = graph_repo
    app.state.bm25_retriever = bm25
    app.state.reranker = reranker
    app.state.agent_runtime = agent_runtime
    app.state.semantic_cache = semantic_cache
    app.state.circuit_breaker = circuit_breaker
    app.state.chat_orchestrator = chat_orchestrator

    logger.info("KAgent initialized and ready on POST /api/v1/gateway/stream")

    try:
        yield
    finally:
        await chat_orchestrator.drain_background_tasks()
        await router.print_session_summary()
        results = await asyncio.gather(
            mcp_registry.close_all(),
            provider_factory.close(),
            semantic_cache.close(),
            qdrant_store.close(),
            graph_repo.close(),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, BaseException):
                logger.warning("Shutdown cleanup failed: %s", result)
        logger.info("KAgent shutdown complete")


app = FastAPI(
    title="KAgent",
    description="Enterprise LLM gateway with unified routing and cost control",
    version="0.3.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """全局验证 JWT 或 API Key，并把身份写入 request.state。"""
    path = request.url.path
    if path in PUBLIC_PATHS:
        return await call_next(request)

    auth_header = request.headers.get("Authorization", "")
    api_key_header = request.headers.get("X-API-Key")
    if auth_header.startswith("Bearer ") and auth_header[7:].strip():
        try:
            request.state.user = verify_token(auth_header[7:].strip())
            request.state.auth_method = "jwt"
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers={"WWW-Authenticate": "Bearer"},
            )
        return await call_next(request)

    if api_key_header is not None and config.api_key:
        try:
            request.state.user = verify_api_key_value(api_key_header)
            request.state.auth_method = "api_key"
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
            )
        return await call_next(request)

    if api_key_header is not None and not config.api_key:
        return JSONResponse(
            status_code=401,
            content={"detail": "API Key 认证未启用"},
        )

    return JSONResponse(
        status_code=401,
        content={"detail": "缺少认证信息，请提供 Bearer token 或 X-API-Key"},
        headers={"WWW-Authenticate": "Bearer"},
    )


app.include_router(token_router)
app.include_router(gateway_router)
app.include_router(monitor_router)


@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/gateway/metrics", tags=["observability"])
async def gateway_metrics() -> dict:
    metrics = build_metrics_payload(getattr(app.state, "semantic_cache", None))
    cb_stats = app.state.circuit_breaker.stats() if hasattr(app.state, "circuit_breaker") else {}
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - _start_time, 0),
        "metrics": metrics,
        "circuit_breaker": cb_stats,
    }


limiter = Limiter(
    key_func=get_remote_address,
    application_limits=[f"{config.rate_limit_per_minute}/minute"],
    enabled=config.rate_limit_enabled,
    headers_enabled=True,
)
for route in app.routes:
    if getattr(route, "path", None) in PUBLIC_PATHS and hasattr(route, "endpoint"):
        limiter.exempt(route.endpoint)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


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
