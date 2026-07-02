# KGateway 解耦重构 Spec

## 1. 目标

在**不破坏现有功能**的前提下，把 KGateway 从“路由层拼装一切”的结构，重构为“API 层 + 应用编排层 + 策略层 + 基础设施适配层”的解耦架构。

核心目标：

- 去掉全局状态和隐式依赖
- 让业务编排独立于传输层和存储实现
- 让缓存、检索、路由、Agent、观测可替换
- 保持现有 SSE 聊天、指标、熔断、trace 功能可用

## 2. 当前根因

当前主要耦合不是单点代码风格问题，而是边界缺失：

1. `routes.py` 同时承担 API、编排、策略、流式、观测职责
2. `main.py` 通过全局注入把对象散落到模块级变量
3. `AgentRuntime` 直接依赖 RAG 注入函数，Planner 还混有策略逻辑
4. Redis / Qdrant / BM25 中混入了租户、部门、隔离等业务规则
5. 前端直接依赖后端路径和 SSE 帧结构，缺少稳定契约

## 3. 目标架构

### 3.1 分层

- API 层
  - 只负责请求接收、响应输出、SSE 传输

- Application 层
  - 负责完整业务编排
  - 例如 `ChatOrchestrator`

- Domain / Policy 层
  - 路由策略
  - 隔离策略
  - 缓存命中策略
  - Agent 决策策略

- Infrastructure 层
  - Redis
  - Qdrant
  - Neo4j
  - LLM API
  - LangFuse

### 3.2 依赖方向

原则：

- 上层依赖下层接口，不直接依赖实现
- 基础设施只能实现接口，不能反向调用业务层
- API 层不持有业务状态，只负责转发

## 4. 拆解范围

### 4.1 必须拆的点

1. `routes.py` 变薄
2. 去掉模块级全局对象依赖
3. 把 RAG、缓存、熔断、流式生成抽成独立服务
4. Agent 的工具调用改为显式注册
5. 前后端接口建立统一契约

### 4.2 暂不重写的点

- 不改外部 API 路径的语义
- 不改现有 SSE 帧格式的基本结构
- 不做大规模 UI 重构
- 不推倒重做数据存储

## 5. 设计方案

### 5.1 ChatOrchestrator

新增一个应用编排中心：

- 输入：`GatewayRequest` + `RequestContext`
- 输出：SSE 事件流或统一的流式结果对象

职责：

1. 检查熔断
2. 查语义缓存
3. 调用 Agent / RAG
4. 调用 LLM 流式生成
5. 写入缓存
6. 上报 trace / metrics

### 5.2 端口接口

为核心能力定义接口：

- `IRoutingService`
- `ICacheService`
- `IRagService`
- `IAgentService`
- `ILLMStreamClient`
- `ITraceService`
- `ICircuitBreaker`

### 5.3 适配器实现

基础设施实现只做适配：

- `RedisSemanticCacheAdapter`
- `QdrantRagAdapter`
- `Bm25RetrieverAdapter`
- `DeepSeekStreamClient`
- `LangfuseTraceAdapter`
- `LocalMetricsAdapter`

### 5.4 策略对象

把规则从实现里抽出来：

- `ModelRoutingPolicy`
- `TenantIsolationPolicy`
- `CacheMatchPolicy`
- `AgentPlanPolicy`

默认策略先完全复用当前逻辑，保证行为不变。

## 6. 迁移阶段

### Phase 1: 只立边界

目标：

- 新增 `ChatOrchestrator`
- `routes.py` 改为只调用 orchestrator
- 先不动现有算法逻辑

验收：

- 现有 `/api/v1/gateway/stream` 仍可用
- SSE 输出不变
- 聊天功能不回退

### Phase 2: 抽服务

目标：

- 把缓存、RAG、流式 LLM、trace 拆成独立服务
- `routes.py` 不再直接碰这些实现

验收：

- 代码中不再依赖一堆模块级全局变量
- 每个能力可单测

### Phase 3: 抽策略

目标：

- 把模型路由、租户隔离、缓存命中、Agent 决策规则独立出来

验收：

- 策略可替换
- 存储层不再写业务规则

### Phase 4: 契约统一

目标：

- 前后端接口契约版本化
- SSE 帧定义明确
- 补齐监控接口

验收：

- Dashboard 不再依赖错误路径
- 聊天页与后端帧协议一致

## 7. 风险与控制

### 风险 1：行为漂移

控制方式：

- 保留旧接口
- 保留旧 SSE 格式
- 先做包装，不先改输出

### 风险 2：拆完功能断

控制方式：

- 每个阶段都可单独回退
- 每个服务都有最小单测

### 风险 3：前后端契约不一致

控制方式：

- 先生成契约，再改实现
- 旧接口加兼容层

## 8. 验收标准

满足以下条件，才算这次解耦有效：

1. `routes.py` 只做请求转发和响应封装
2. 不再依赖模块级全局变量进行业务编排
3. 缓存、RAG、Agent、LLM、trace 都能独立替换
4. 现有聊天功能保持可用
5. dashboard / breaker / traces 页面能继续工作
6. 关键流程有最小单元测试覆盖

## 9. 建议的最终落地顺序

1. 先加 `ChatOrchestrator`
2. 再把 `routes.py` 变薄
3. 然后抽服务接口
4. 再抽策略
5. 最后统一前后端契约

## 10. 需要你拍板的点

1. 是否接受以 `ChatOrchestrator` 作为唯一业务入口
2. 是否接受旧接口先保留兼容层
3. 是否接受分阶段迁移，而不是一次性重写
4. 是否接受先不动 UI，只补契约和后端边界

