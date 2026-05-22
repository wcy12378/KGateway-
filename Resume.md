# 王辰宇

**电话:** 13797390580 | **邮箱:** 2040188027@qq.com | **GitHub:** [项目已开源，面试时提供远程查阅]

---

## 教育背景

**武昌首义学院** — 计算机科学与技术（华为云班） | 本科在读
*2023.09 - 2027.06*

---

## 专业技能

**AI 后端与并发:** Python asyncio 非阻塞编程, 协程并发与线程池隔离调优, HTTP SSE 流式传输, TCP 背压机制

**RAG 与检索优化:** 双阶段混合召回 (Dense/Sparse), RRF 倒数排名融合, Cross-Encoder 精排, 向量语义缓存 (VSS)

**Agent 与智能体:** 状态机 (FSM) 架构, ReAct 确定性运行时, Tool Calling 机制, 任务规划与迭代控制

**文档解析与 ETL:** 多模态文档解析, 长上下文切分策略, 表格防断裂机制, VLM 图像语义提取

**云原生与中间件:** FastAPI, Redis / Qdrant / Neo4j, Celery 分布式调度, Docker / MinIO

---

## 项目经历

### KGateway - 企业级混合多模态 Agent 知识库网关 | AI 后端研发
*2026.04 - 2026.05*

面向企业大模型落地场景的 AI 基础设施网关，基于 FastAPI 构建流式异步管道，解决长尾延迟、Token 成本高及多租户隔离问题。

**Tech Stack:** FastAPI, Qdrant, Redis, Neo4j, BGE-Reranker, LangFuse, Locust

- 设计 HTTP SSE 双向解耦流式网关，实现「状态流 + 文本流」架构；基于 asyncio.wait(FIRST_COMPLETED) 实现双路竞速守护机制，在模型思考期维持 200ms 高频客户端心跳检测。检测到客户端离线后，显式调用 pending_task.cancel() 并通过 CancelledError 异常传导链显式回收 pending 协程，强杀上游 HTTP/2 RST_STREAM 帧，从根本上杜绝孤儿 Task 驻留事件循环引发的内存泄漏，毫秒级终止上游计费，减少无效 Token 消耗。

- 基于 Qdrant HNSW 索引原生 Filter 实现 AND 逻辑预过滤位图剪枝，在索引遍历阶段完成租户数据硬隔离，规避后过滤导致的召回率衰减问题。

- 构建 Dense/Sparse 双阶段混排管线：采用 2-gram 倒排索引 + RRF 融合算法（k=60）动态排序；通过 asyncio.to_thread 安全卸载 BGE-Reranker 精排推理，避免阻塞主事件循环。

- 摒弃黑盒框架，基于 FSM 状态机自研确定性 Agent 运行时（Planner → Tool Executor → Fallback），注入最大 4 次迭代沙箱，显著降低无限循环风险。

- 自研 Closed/Open/Half-Open 三态自修复熔断器，基于 60s 滑动窗口（10次错误率阈值）动态检测下游 API 状态；在 Half-Open 状态下通过单并发请求进行动态探测自修复，防止高并发下游 API 速率限制（429）雪崩蔓延。

- 实现 RediSearch 向量语义缓存，对语义相似度 >0.96 的请求实现 5ms 内无损拦截，显著降低 Token 财务成本。

**量化压测成果:**
- 经 Locust 分布式压力测试验证，在支持 200 并发 SSE 长连接的极限压测基准下，热路径命中向量语义缓存（VSS）实现 5ms 内无损拦截，冷路径 P99 首包延迟（TTFT）稳定压制在 45ms 内。
- 在 1000 QPS 压测基准下，基于 1000 条真实测试集调参确立 0.96 向量相似度阈值，语义缓存最高命中率达 68.4%，使单日 Token 财务成本降低 42.6%。

---

### OmniParse - 企业级异步多模态文档解析与 ETL 引擎 | AI 数据架构
*2026.03 - 2026.04*

面向大模型异构知识库场景的分布式数据清洗与入库流水线，支持复杂 PDF、跨页表格等多源数据，提升脏数据结构化提取的准确率。

**Tech Stack:** Celery, Redis, MinIO, Unstructured, Qdrant, Docker Compose

- 设计 FastAPI + Celery 分布式异步解耦架构，将耗时文件解析从主业务分离。将轻量级 VLM 推理以进程级常驻方式部署于独立算力队列 Worker，通过配置 CELERYD_MAX_TASKS_PER_CHILD=50 定期强行回收子进程，规避显存碎片累积引发的 CUDA OOM 风险。

- 自研格式感知切分器 EnterpriseChunker，支持大文件分片传入推理队列并限制单批次图片数量，将空间复杂度稳稳压制在 O(1)。在切分阶段将跨页表格整体还原为完整的 Markdown/HTML 结构作为 Parent Doc，利用轻量级 LLM 生成摘要作为 Child Chunk 入库并保留指针（父子文档策略），显著降低因语义截断引发的模型幻觉率。

- 在结构化解析阶段透传 PDF 内嵌图片至轻量级 VLM 生成 Image Caption，完成富文本原位合并，保留长上下文图文关联性。

- 设计全流式 Generator Pipeline，将 Qdrant 入库控制在 100 points/batch，高并发场景空间复杂度压制至 O(1)；基于 Docker Compose 实现多级 Worker 一键部署。

- 高并发场景下任务提交 P99 延迟 < 20ms。
