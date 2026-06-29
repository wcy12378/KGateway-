/**
 * 使用说明页面。
 *
 * 本文件负责解释控制台各模块用途、操作方法和状态含义。它不负责拉取后端数据、
 * 修改网关配置或执行业务操作。
 */
import {
  BarChart3,
  BookOpen,
  History,
  MessageSquare,
  Settings2,
  Shield,
} from 'lucide-react';

interface GuideSection {
  title: string;
  subtitle: string;
  icon: typeof MessageSquare;
  points: string[];
  usage: string[];
}

const SECTIONS: GuideSection[] = [
  {
    title: '智能对话',
    subtitle: '通过 SSE 流式调用网关，查看模型实时回复。',
    icon: MessageSquare,
    points: [
      '用于向 KAgent 发送用户问题，并实时接收模型生成内容。',
      '支持普通问答和高级推理模式，具体请求会携带用户、租户、部门和会话信息。',
      '回答下方会展示模型、Token、延迟、成本、缓存和 trace_id 等元数据。',
    ],
    usage: [
      '先在左侧参数面板确认用户 ID、租户 ID 和部门。',
      '在底部输入框输入问题，按 Enter 发送，Shift+Enter 换行。',
      '生成过程中可以点击“停止”中断当前请求。',
    ],
  },
  {
    title: '请求参数',
    subtitle: '控制每次聊天请求携带的身份、租户和路由信息。',
    icon: Settings2,
    points: [
      '用户 ID 用于标识本次请求的使用者。',
      '租户 ID 用于多租户隔离，后端会基于租户控制检索和缓存边界。',
      '部门会影响权限、数据范围或后续审计维度。',
      '高级推理开启后，会优先路由到更强但成本更高的推理模型。',
    ],
    usage: [
      '修改参数后无需单独保存，下一次发送问题时会自动使用最新参数。',
      '会话 ID 为只读字段，用于串联同一轮对话和 trace。',
      '移动端点击页面顶部参数按钮可打开或关闭参数抽屉。',
    ],
  },
  {
    title: '运行指标',
    subtitle: '查看网关整体吞吐、缓存、Token、成本和延迟分布。',
    icon: BarChart3,
    points: [
      '请求总数用于观察网关累计处理量。',
      '缓存命中率用于判断语义缓存是否有效降低调用成本。',
      'Token 消耗和预估成本用于追踪模型资源使用。',
      '延迟分布用于判断请求主要集中在哪个耗时区间。',
    ],
    usage: [
      '可选择自动刷新频率，也可以手动点击“刷新”。',
      '后端未启动时会出现 HTTP 502，这是代理无法连接后端的提示。',
      '最近请求表会展示最近 20 条请求的用户、部门、缓存和延迟。',
    ],
  },
  {
    title: '链路追踪',
    subtitle: '按请求查看 trace 列表、筛选条件和每个阶段耗时。',
    icon: History,
    points: [
      '用于排查一次请求在熔断、缓存、检索、精排和 Agent 执行阶段的耗时。',
      '支持按 trace_id、部门、缓存状态、模型和延迟排序过滤。',
      '展开一行后可以查看元数据、阶段耗时瀑布图和原始 JSON。',
    ],
    usage: [
      '通过搜索框输入 trace_id 片段定位请求。',
      '点击表格行展开或收起详情。',
      '点击“复制 Trace ID”可将标识复制给后端或运维排查。',
    ],
  },
  {
    title: '熔断器',
    subtitle: '查看并控制网关保护状态，防止下游异常扩大。',
    icon: Shield,
    points: [
      '已关闭表示请求正常转发。',
      '已开启表示熔断生效，请求会被拒绝。',
      '半开启表示系统正在探测恢复，仅放行部分请求。',
      '失败次数达到阈值后，熔断器会进入保护状态。',
    ],
    usage: [
      '点击“刷新”获取最新状态。',
      '“强制开启熔断”用于主动停止请求转发。',
      '“强制关闭熔断”只应在确认下游恢复后使用。',
    ],
  },
  {
    title: '历史会话',
    subtitle: '管理本地保存的聊天会话入口。',
    icon: BookOpen,
    points: [
      '会话列表保存在浏览器本地存储中，主要用于切换当前会话 ID。',
      '新建会话会清空当前消息，并生成新的会话 ID。',
      '删除会话只影响本地列表，不会删除后端 trace 数据。',
    ],
    usage: [
      '点击加号新建会话。',
      '点击某个会话可切换当前会话。',
      '鼠标悬停在会话上可显示删除按钮。',
    ],
  },
];

export default function GuidePage() {
  return (
    <div>
      <div className="mb-5 border-b border-crt-border pb-4">
        <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:gap-4">
          <h1 className="font-macro text-[clamp(2rem,5vw,3.5rem)] leading-none text-crt-fg">
            使用说明
          </h1>
          <span className="font-label text-crt-fg-muted">
            模块说明与操作指南
          </span>
        </div>
        <p className="mt-3 max-w-3xl text-[13px] leading-6 text-crt-fg-dim">
          本页面用于解释 KAgent 控制台每个模块的作用、使用方式和常见状态。
          如果页面出现“请求失败（HTTP 502）”，通常表示前端代理无法连接后端
          FastAPI 服务，需要先启动 8000 端口的后端。
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        {SECTIONS.map((section) => (
          <section
            key={section.title}
            className="rounded-lg border border-crt-border bg-crt-bg-elevated p-4"
          >
            <div className="mb-4 flex items-start gap-3">
              <div className="icon-button shrink-0">
                <section.icon size={17} aria-hidden="true" />
              </div>
              <div>
                <h2 className="font-macro text-[22px] leading-tight text-crt-fg">
                  {section.title}
                </h2>
                <p className="mt-1 text-[13px] leading-5 text-crt-fg-muted">
                  {section.subtitle}
                </p>
              </div>
            </div>

            <div className="grid gap-3 lg:grid-cols-2">
              <div>
                <div className="font-label mb-2 text-crt-fg-muted">模块作用</div>
                <ul className="space-y-2 text-[13px] leading-5 text-crt-fg-dim">
                  {section.points.map((item) => (
                    <li key={item} className="rounded-md bg-crt-bg/50 px-3 py-2">
                      {item}
                    </li>
                  ))}
                </ul>
              </div>

              <div>
                <div className="font-label mb-2 text-crt-fg-muted">如何使用</div>
                <ol className="space-y-2 text-[13px] leading-5 text-crt-fg-dim">
                  {section.usage.map((item, index) => (
                    <li key={item} className="flex gap-2 rounded-md bg-crt-bg/50 px-3 py-2">
                      <span className="font-mono text-crt-border-strong">
                        {index + 1}.
                      </span>
                      <span>{item}</span>
                    </li>
                  ))}
                </ol>
              </div>
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
