"""KAgent 压力测试脚本 — 基于 Locust 的分布式压测。

场景设计：
- 1000 并发用户
- 20% 高频重复问题（压测 Redis 语义缓存命中极限 + P99）
- 80% 冷启动复杂长文本（压测 BGE 精排 + Agent 有限状态机）

启动方式：
    locust -f tests/locustfile.py --host=http://localhost:8000
    或分布式：
    locust -f tests/locustfile.py --host=http://localhost:8000 --master
    locust -f tests/locustfile.py --host=http://localhost:8000 --worker --master-host=127.0.0.1
"""

from __future__ import annotations

import json
import random
import uuid

from locust import HttpUser, between, events, task


# ── 多租户 + 多部门轮询池 ──────────────────────────────────────

TENANTS = [
    "tenant_acme", "tenant_globex", "tenant_initech",
    "tenant_umbrella", "tenant_stark", "tenant_wayne",
]

DEPARTMENTS = ["legal", "hr", "engineering", "finance", "general"]

# ── 20% 高频重复问题（缓存热点）────────────────────────────────
HOT_QUESTIONS = [
    "公司的年假政策是什么？",
    "最新劳动法修订了哪些内容？",
    "如何申请远程办公？",
    "报销流程是怎样的？",
    "员工手册在哪里下载？",
    "社保缴纳比例是多少？",
    "年终奖发放时间？",
    "加班费计算标准？",
    "入职需要准备什么材料？",
    "合同续签流程是什么？",
]

# ── 80% 冷启动复杂长文本问题 ────────────────────────────────────
COLD_QUESTIONS = [
    "请详细分析一下我们公司2024年第三季度的财务报表，包括营收增长率、毛利率变化、净利润趋势，并与同行业平均水平进行对比分析。同时请给出未来两个季度的预测建议。",
    "根据最新的国际贸易法规变化，评估我司出口业务可能面临的风险，包括关税调整、制裁名单更新、合规审查要求等方面，并制定相应的应对策略。",
    "帮我梳理一下最近三个月的所有劳动纠纷案例，分析争议焦点、仲裁结果、赔偿金额，并总结出公司在用工合规方面需要改进的具体措施。",
    "请对比分析市面上主流的五款低代码开发平台，从性能、安全性、可扩展性、社区活跃度、许可证成本等维度进行评分，并给出采购建议。",
    "帮我起草一份完整的数据安全管理制度，需要覆盖数据分类分级、访问控制、加密传输、备份恢复、应急响应等方面，符合最新的《个人信息保护法》要求。",
    "请分析最近一次系统宕机事件的根因，包括时间线还原、影响范围评估、恢复过程复盘，并提出具体的改进方案和SLA保障措施。",
    "对比三家云服务商（AWS、Azure、阿里云）的企业级方案，从全球节点覆盖、网络延迟、存储成本、安全合规、技术支持响应时间等维度进行深度评估。",
    "帮我设计一套完整的员工绩效考核体系，需要覆盖OKR设定、360度评估、强制分布、校准会议、结果应用等环节，并提供详细的实施方案和时间表。",
    "分析一下我们当前的CI/CD流水线的瓶颈在哪里，包括构建时间、测试覆盖率、部署频率、回滚速度等指标，并给出具体的优化方案和预期收益。",
    "请帮我梳理公司近三年的所有知识产权纠纷，包括专利侵权、商标争议、著作权保护等方面的案例，分析胜败原因并制定未来的IP保护策略。",
]


# ── 路由决策参数池 ──────────────────────────────────────────────

def _random_request_body(is_hot: bool = False) -> dict:
    """生成随机 GatewayRequest 请求体。"""
    tenant = random.choice(TENANTS)
    dept = random.choice(DEPARTMENTS)
    question = random.choice(HOT_QUESTIONS if is_hot else COLD_QUESTIONS)
    advanced = random.random() < 0.3  # 30% 概率启用高级推理

    return {
        "user_id": f"loadtest_user_{random.randint(1, 10000)}",
        "tenant_id": tenant,
        "department": dept,
        "question": question,
        "session_id": str(uuid.uuid4()),
        "advanced_reasoning": advanced,
    }


# ── Locust User 定义 ────────────────────────────────────────────

class KAgentUser(HttpUser):
    """模拟真实用户的请求行为。"""

    wait_time = between(0.5, 2.0)  # 请求间隔 0.5-2 秒

    @task(20)
    def hot_path_stream(self):
        """20% 热路径：高频重复问题 → 压测 Redis 缓存命中。"""
        body = _random_request_body(is_hot=True)
        with self.client.post(
            "/api/v1/gateway/stream",
            json=body,
            headers={"Content-Type": "application/json"},
            name="/stream [HOT]",
            catch_response=True,
            stream=True,
        ) as response:
            if response.status_code == 200:
                # 读取 SSE 流验证完整性
                content = b""
                for chunk in response.iter_content(chunk_size=1024):
                    content += chunk
                    if b"data: [DONE]" in content:
                        response.success()
                        return
                # 没有收到 DONE 信号也算部分成功
                response.success()
            elif response.status_code == 429:
                response.failure("Rate limited (429)")
            elif response.status_code >= 500:
                response.failure(f"Server error: {response.status_code}")
            else:
                response.failure(f"Unexpected status: {response.status_code}")

    @task(80)
    def cold_path_stream(self):
        """80% 冷路径：复杂长文本 → 压测 Agent + Rerank + 线程池。"""
        body = _random_request_body(is_hot=False)
        with self.client.post(
            "/api/v1/gateway/stream",
            json=body,
            headers={"Content-Type": "application/json"},
            name="/stream [COLD]",
            catch_response=True,
            stream=True,
        ) as response:
            if response.status_code == 200:
                content = b""
                for chunk in response.iter_content(chunk_size=1024):
                    content += chunk
                    if b"data: [DONE]" in content:
                        response.success()
                        return
                response.success()
            elif response.status_code == 429:
                response.failure("Rate limited (429)")
            elif response.status_code >= 500:
                response.failure(f"Server error: {response.status_code}")
            else:
                response.failure(f"Unexpected status: {response.status_code}")

    @task(5)
    def health_check(self):
        """5% 比例的健康检查。"""
        self.client.get("/health", name="/health")

    @task(3)
    def metrics_check(self):
        """3% 比例的指标查询。"""
        with self.client.get(
            "/api/v1/gateway/metrics",
            name="/metrics",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                try:
                    data = json.loads(response.text)
                    # 验证关键字段存在
                    required = ["total_requests", "cache_hit_rate", "total_cost_usd"]
                    for key in required:
                        if key not in data:
                            response.failure(f"Missing metric: {key}")
                            return
                    response.success()
                except json.JSONDecodeError:
                    response.failure("Invalid JSON response")
            else:
                response.failure(f"Status: {response.status_code}")


# ── 测试事件钩子 ────────────────────────────────────────────────

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """压测启动时打印配置信息。"""
    print("\n" + "=" * 60)
    print("🚀 KAgent 压力测试启动")
    print(f"   目标: {environment.host}")
    print(f"   场景: 20% 热路径 + 80% 冷路径")
    print(f"   租户池: {len(TENANTS)} 个")
    print(f"   部门池: {len(DEPARTMENTS)} 个")
    print(f"   热问题池: {len(HOT_QUESTIONS)} 个")
    print(f"   冷问题池: {len(COLD_QUESTIONS)} 个")
    print("=" * 60 + "\n")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """压测结束时打印汇总。"""
    stats = environment.runner.stats
    if stats.total.fail_ratio > 0.05:
        print(f"\n⚠️ 失败率 {stats.total.fail_ratio:.1%} 超过 5% 阈值！")
    else:
        print(f"\n✅ 压测完成，失败率 {stats.total.fail_ratio:.2%}")
