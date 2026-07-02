# KAgent 升级总纲

## 定位
**KAgent** — 企业级 AI Agent 编排平台

核心理念：让 AI Agent 真正工作在企业的工具和知识之上。原生 MCP 协议支持、多 Provider Tool Calling、多租户隔离、全链路可观测。

---

## 升级路线（4 个 Phase）

### Phase 0：重塑骨架与基础能力（4 天）
**目标：** 把项目从"能跑的 demo"变成"能演示的产品"——改名 + 去 mock + 可部署

| 任务 | 描述 | 交付物 |
|------|------|--------|
| P0-1 | 项目改名 KAgent，重构目录结构 | 新的项目命名和目录 |
| P0-2 | 抽象 LLM Provider 层，支持 DeepSeek/OpenAI/Google 一键切换 | `LLMProvider` 接口 + 3 个实现 |
| P0-3 | Agent 从 FSM if-else 改为真实 Tool Calling | 注册式工具体系 + ReAct 循环 |
| P0-4 | 去 mock Dense 检索，接入真实 Qdrant | 真实向量检索链路 |
| P0-5 | 加 JWT 认证 | API 安全中间件 |
| P0-6 | 修复前后端接口对齐 | Dashboard/Traces 真实工作 |
| P0-7 | 接入 1 个真实 MCP Server demo | MCP 工具调用链路 |
| P0-8 | 重写 README，生成 Demo 视频 | GitHub 首页 |

### Phase 1：工程化加固（1 周）
**目标：** 让面试官相信这项目不是玩具

| 任务 | 描述 |
|------|------|
| P1-1 | GitHub Actions CI（lint + test + build） |
| P1-2 | Rate limiting + API Key 管理 |
| P1-3 | 核心链路单元测试（ChatOrchestrator） |
| P1-4 | Locust 压测 + 报告 |
| P1-5 | Docker Compose 生产化（健康检查、日志、重启策略） |
| P1-6 | 完善的错误处理和日志分级 |

### Phase 2：多 Agent 与高级能力（1 周）
**目标：** 展示真正的 AI Agent 平台深度

| 任务 | 描述 |
|------|------|
| P2-1 | 多 Agent 工作流（顺序 / 并行 / 路由） |
| P2-2 | Agent Memory（短期 + 长期向量记忆） |
| P2-3 | 多 Provider 自动路由与 fallback |
| P2-4 | Prompt 模板管理与版本化 |
| P2-5 | 工具调用审计日志 |

### Phase 3：产品化与面试包装（3 天）
**目标：** 让项目在简历和面试中最大化冲击力

| 任务 | 描述 |
|------|------|
| P3-1 | 前端科技蓝重设计 |
| P3-2 | 精修 README + 架构图 + 技术博客 |
| P3-3 | 录制 3 分钟 Demo 视频 |
| P3-4 | 部署到公网可访问 |
| P3-5 | 面试话术梳理（逐技术点准备） |

---

## 架构目标（最终态）

```
┌──────────────────────────────────────────────────────────┐
│                     KAgent Platform                       │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐ │
│  │  React 前端   │  │  FastAPI     │  │  MCP Server    │ │
│  │  Chat/Traces │  │  REST API    │  │  注册中心       │ │
│  │  Dashboard   │  │  SSE Stream  │  │                │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬─────────┘ │
│         │                 │                 │            │
│         ▼                 ▼                 ▼            │
│  ┌──────────────────────────────────────────────────┐    │
│  │              Application Layer                    │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │    │
│  │  │Agent     │  │Workflow  │  │Tool Registry │   │    │
│  │  │Runtime   │  │Engine    │  │(MCP + 本地)  │   │    │
│  │  └──────────┘  └──────────┘  └──────────────┘   │    │
│  └──────────────────────────────────────────────────┘    │
│                         │                                │
│                         ▼                                │
│  ┌──────────────────────────────────────────────────┐    │
│  │              LLM Provider Layer                   │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │    │
│  │  │DeepSeek  │  │OpenAI    │  │Google Gemini │   │    │
│  │  │Provider  │  │Provider  │  │Provider      │   │    │
│  │  └──────────┘  └──────────┘  └──────────────┘   │    │
│  └──────────────────────────────────────────────────┘    │
│                         │                                │
│                         ▼                                │
│  ┌──────────────────────────────────────────────────┐    │
│  │            Infrastructure Layer                   │    │
│  │  Qdrant  │  Redis  │  Neo4j  │  LangFuse         │    │
│  └──────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────┘
```

---

## Phase 0 详细任务单（当前执行）

### P0-1：项目改名 KAgent
**修改清单：**
- [ ] 后端 `src/main.py` — FastAPI title "KGateway" → "KAgent"
- [ ] 后端 `src/config.py` — 配置前缀 KGW_ → KAGENT_
- [ ] 前端 `package.json` — name "frontend" → "kagent-frontend"
- [ ] 前端 `src/layouts/AppLayout.tsx` — "KGATEWAY" → "KAGENT"
- [ ] README 全面重写
- [ ] docker-compose 容器名 kgw-* → kagent-*

### P0-2：LLM Provider 抽象层
**新建文件：**
- [ ] `src/core/providers/__init__.py`
- [ ] `src/core/providers/base.py` — `LLMProvider` 抽象基类
- [ ] `src/core/providers/deepseek.py`
- [ ] `src/core/providers/openai.py`
- [ ] `src/core/providers/gemini.py`

**修改文件：**
- [ ] `src/core/schemas.py` — 加 Provider 枚举
- [ ] `src/config.py` — 加多 Provider 配置
- [ ] `src/application/streaming_tasks.py` — 迁移到 Provider 调用

### P0-3：Agent 重构为 Tool Calling
**新建文件：**
- [ ] `src/core/tools/__init__.py`
- [ ] `src/core/tools/registry.py` — `@tool` 装饰器 + ToolRegistry
- [ ] `src/core/tools/builtin.py` — query_knowledge, web_search, calculator 等内置工具
- [ ] `src/core/agent/__init__.py`
- [ ] `src/core/agent/react_agent.py` — ReAct 循环引擎

**修改文件：**
- [ ] `src/agents/runtime.py` — 改为调用 ReActAgent
- [ ] `src/application/orchestrator.py` — Agent 调用更新
- [ ] 前端 SSE 解析 — 加 `agent_thought` 字段展示

### P0-4：去 mock Qdrant
**修改文件：**
- [ ] `src/application/rag_service.py` — 替换 `_mock_dense_search()`
- [ ] 新建 `scripts/seed_qdrant.py` — 数据灌入脚本

### P0-5：JWT 认证
**新建文件：**
- [ ] `src/api/auth.py` — JWT 签发 + 验证依赖

**修改文件：**
- [ ] `src/main.py` — 注册 auth 中间件
- [ ] `src/api/routes.py` — 路由加鉴权
- [ ] `.env.example` — 加 JWT 配置
- [ ] 前端 `gateway.ts` — 请求头加 Authorization

### P0-6：前后端接口对齐
**修改文件：**
- [ ] 前端 `src/lib/gateway.ts` — 确认所有 endpoint 正确
- [ ] 前端 `src/lib/http.ts` — 统一错误处理
- [ ] 修复 Dashboard/Traces/Breaker 页面错误状态

### P0-7：MCP Server 接入
**新建文件：**
- [ ] `src/core/mcp/__init__.py`
- [ ] `src/core/mcp/client.py` — MCP 协议客户端
- [ ] `src/core/mcp/server_registry.py` — MCP Server 注册管理
- [ ] `src/core/tools/mcp_tools.py` — MCP 工具适配桥

### P0-8：README + Demo
- [ ] 重写 README.md（中英双语文档顶部）
- [ ] 录制 3 分钟 Demo GIF
- [ ] 生成架构图
