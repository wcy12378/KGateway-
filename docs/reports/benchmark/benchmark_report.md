# KAgent 真实模型压测报告

## 测试说明

本报告记录 2026-06-29 在本地开发环境执行的真实模型 Locust 压测。KAgent 使用根目录 `.env` 中配置的 DeepSeek API Key，请求实际访问 DeepSeek API，未压测生产环境。

- [真实模型 Locust HTML 报告](./benchmark_report_prod.html)
- [P1-4 降级链路 HTML 基线](./benchmark_report.html)

## Provider 验证

| Provider | 模型 | 验证结果 | 是否参与压测 |
|---|---|---|---|
| DeepSeek | `deepseek-v4-flash` | 普通与流式请求均成功 | 是 |
| OpenAI | `gpt-4o-mini` | HTTP 429，账户 `insufficient_quota` | 否 |
| Gemini | `gemini-2.0-flash` | HTTP 429，该模型免费额度为 0 | 否 |

OpenAI 与 Gemini 的失败原因均为账户配额，不是模型名不匹配。本次压测只使用项目默认 Provider DeepSeek，API 地址为 `https://api.deepseek.com/v1/chat/completions`。

## 测试环境

| 项目 | 配置 |
|---|---|
| 操作系统 | Windows 11 家庭版 |
| CPU | Intel Core i5-13500HX，20 逻辑处理器 |
| 内存 | 15.7 GB |
| Python | 3.12.13 |
| Locust | 2.44.4 |
| 后端 | Uvicorn，单进程，本机 `127.0.0.1:8000` |
| 基础设施 | Docker Qdrant + Redis Stack |
| 本地模型 | `BAAI/bge-base-zh-v1.5` Embedding + `BAAI/bge-reranker-base`，CPU |
| 并发用户数 | 50 |
| 用户生成速率 | 5 用户/秒 |
| 运行时间 | 3 分钟 |
| 流式请求比例 | 热路径约 20%，冷路径约 80% |
| 认证 | 每个虚拟用户独立开发 JWT |
| Rate Limiting | 关闭；本地虚拟用户共享同一源 IP，避免 429 干扰模型链路基准 |
| Neo4j | 未启动，不在本次链路范围内 |

正式压测前已完成模型预热。Locust 流式请求延迟从发送请求开始计算，直到读取 SSE `[DONE]`，包含 Agent、真实 LLM、Embedding、缓存与完整流式传输耗时。

## 真实模型结果摘要

| 指标 | 值 |
|---|---:|
| 总请求数 | 645 |
| 失败请求数 | 0 |
| 失败率 | 0.00% |
| 平均延迟 | 11.62 s |
| P50 延迟 | 8.9 s |
| P95 延迟 | 31 s |
| P99 延迟 | 42 s |
| 最大延迟 | 68.04 s |
| 平均吞吐量 | 3.60 RPS |

## 分接口结果

| 接口 | 请求数 | 失败率 | 平均延迟 | P50 | P95 | P99 | RPS |
|---|---:|---:|---:|---:|---:|---:|---:|
| `/auth/token` | 50 | 0.00% | 145 ms | 59 ms | 490 ms | 490 ms | 0.28 |
| `/health` | 30 | 0.00% | 65 ms | 25 ms | 340 ms | 350 ms | 0.17 |
| `/metrics` | 12 | 0.00% | 36 ms | 12 ms | 150 ms | 150 ms | 0.07 |
| `/stream [COLD]` | 427 | 0.00% | 15.11 s | 11 s | 34 s | 44 s | 2.38 |
| `/stream [HOT]` | 126 | 0.00% | 8.22 s | 5.8 s | 19 s | 24 s | 0.70 |

## 与 P1-4 降级基线对比

| 指标 | P1-4 降级基线 | P1-4b 真实 DeepSeek |
|---|---:|---:|
| 并发用户 | 100 | 50 |
| 运行时间 | 2 分钟 | 3 分钟 |
| 总请求数 | 7,620 | 645 |
| 失败率 | 0.00% | 0.00% |
| 平均吞吐量 | 63.70 RPS | 3.60 RPS |
| P50 | 51 ms* | 8.9 s |
| P95 | 230 ms* | 31 s |
| P99 | 300 ms* | 42 s |

\* P1-4 基线运行时，旧版 Locust 脚本在 `stream=True` 下只统计到收到响应头的时间；P1-4b 已修正为读取完整 SSE `[DONE]` 的端到端时间。因此延迟数值不能直接等价比较，吞吐量和失败率仍可作为链路差异参考。

## 结论

真实模型测试在 50 并发用户下完成 645 次请求，无 HTTP、SSE 或 DeepSeek Provider 失败。相比降级基线，吞吐量从 63.70 RPS 降至 3.60 RPS；完整流式请求的聚合 P99 为 42 秒。冷路径需要生成复杂长文本，平均 15.11 秒，明显高于热路径的 8.22 秒。

主要瓶颈是上游 LLM API 的生成时间与输出长度，而不是本地健康检查、认证或 metrics 接口。冷路径最大延迟达到 68.04 秒，后续应按业务 SLA 限制模型输出长度、区分交互式与长任务队列，并持续观察 DeepSeek 的 TTFT、生成速率和限频响应。

## 产物

- `benchmark_report_prod.html`：真实模型 Locust 可视化报告
- `benchmark_prod_data_stats.csv`：真实模型接口聚合数据
- `benchmark_prod_data_stats_history.csv`：真实模型时序数据
- `benchmark_prod_data_failures.csv`：失败记录，本次为空
- `benchmark_prod_data_exceptions.csv`：异常记录，本次为空
- `benchmark_report.html` 与 `benchmark_data_*`：P1-4 降级链路基线

