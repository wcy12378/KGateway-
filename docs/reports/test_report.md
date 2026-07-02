# KAgent 测试报告

> 生成时间：2026-07-02T23:50:02+08:00
> 运行环境：Python 3.14.4 / Windows 11
> DeepSeek E2E：已启用
> DeepSeek 模型：deepseek-v4-flash

## 后端测试概览

执行状态：**通过**

| 指标 | 数值 |
|------|:----:|
| 总测试数 | 142 |
| 通过 | 142 |
| 失败 | 0 |
| 错误 | 0 |
| 跳过 | 0 |
| 耗时 | 12.72s |

## 后端测试覆盖分类

| 模块 | 测试数 | 覆盖内容 |
|:----|:-----:|---------|
| Provider | 11 | 工厂隔离、模型适配、fallback 与连接复用 |
| Agent | 19 | ReAct 工具调用、异常恢复、迭代上限 |
| 编排 | 23 | 熔断降级、缓存路径、RAG 与快速路径 |
| SSE 协议 | 9 | 帧格式、协议版本、心跳与流任务 |
| 安全 | 22 | JWT、API Key、限流、身份与审计 |
| 记忆 | 7 | 记忆存储、检索、隔离与降级 |
| 路由 | 10 | Provider 路由、健康状态与恢复 |
| 工作流 | 7 | 顺序、规则路由、并行与合成 |
| 存储 | 25 | Qdrant、BM25、Neo4j 与语义缓存 |
| E2E | 3 | 真实 DeepSeek Tool Calling |
| 其他 | 6 | 配置、通用契约及未归入上述模块的测试 |

### 跳过项

- 无

## 前端测试

执行状态：**通过**

| 指标 | 数值 |
|------|:----:|
| 测试文件 | 9 |
| 总测试数 | 22 |
| 通过 | 22 |
| 失败 | 0 |
| 跳过 | 0 |
| 耗时 | 4.80s |

## 前端构建

执行状态：**通过**

```text
dist/assets/vendor-highlighter-CJduBF1d.js    68.40 kB │ gzip:  23.83 kB
dist/assets/vendor-markdown-7dDPWMeW.js      135.56 kB │ gzip:  39.88 kB
dist/assets/vendor-react-BPl2t89V.js         178.32 kB │ gzip:  56.34 kB
dist/assets/vendor-charts-BohjLomB.js        347.30 kB │ gzip: 103.72 kB
✓ built in 1.01s
```

## 复现命令

```powershell
cd 后端
python scripts/generate_test_report.py
```
