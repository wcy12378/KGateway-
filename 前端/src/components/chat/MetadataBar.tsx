import { useState } from 'react';
import { CheckCircle2, ChevronDown, Clock3, Database, FileText, Route } from 'lucide-react';
import type { SSEEvent } from '@/types';

export function MetadataBar({ metadata }: { metadata: SSEEvent }) {
  const [open, setOpen] = useState(false);
  const latency = typeof metadata.total_latency_ms === 'number' ? `${metadata.total_latency_ms} ms` : '已完成';
  const model = metadata.model || '未记录';
  const providerModel = metadata.provider ? `${metadata.provider} · ${model}` : model;
  const sourceLabel = metadata.response_source === 'calculator'
    ? '极速通道 · 计算器'
    : metadata.response_source === 'faq'
      ? '极速通道 · FAQ'
      : metadata.response_source === 'knowledge_unavailable'
        ? '知识库无可用依据'
      : metadata.cache_hit
        ? `${metadata.cache_hit_type === 'exact' ? '精确' : '语义'}缓存命中`
        : `已调用 ${providerModel}`;

  return <div className="mt-3">
    <button onClick={() => setOpen((value) => !value)} className="flex min-h-12 w-full items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50/60 px-4 text-left text-[12px] text-crt-fg-dim" aria-expanded={open}>
      <CheckCircle2 size={17} className="shrink-0 text-emerald-600" />
      <span className="font-semibold text-crt-fg">执行过程</span><span>·</span><span>{sourceLabel}</span><span>·</span><span>{latency}</span>
      <ChevronDown size={15} className={`ml-auto shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
    </button>

    <div className="mt-3 grid gap-3 sm:grid-cols-2">
      <div className="flex min-w-0 items-center gap-3 rounded-xl border border-crt-border bg-white px-4 py-3"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-blue-50 text-blue-700"><Route size={18} /></span><div className="min-w-0"><div className="text-[11px] text-crt-fg-muted">Provider 与实际模型</div><div className="mt-0.5 truncate text-[12px] font-medium text-crt-fg" title={providerModel}>{providerModel}</div></div></div>
      <div className="flex min-w-0 items-center gap-3 rounded-xl border border-crt-border bg-white px-4 py-3"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-emerald-50 text-emerald-700"><FileText size={18} /></span><div className="min-w-0"><div className="text-[11px] text-crt-fg-muted">请求追踪</div><div className="mt-0.5 truncate font-mono text-[11px] text-crt-fg" title={metadata.trace_id}>{metadata.trace_id || '未记录 Trace ID'}</div></div></div>
    </div>

    {open ? <div className="mt-3 grid gap-2 rounded-xl bg-crt-bg p-4 text-[11px] text-crt-fg-dim sm:grid-cols-2">
      <div className="flex items-center gap-2"><Clock3 size={13} />端到端首字：{metadata.ttft_ms ?? 0} ms</div>
      <div>Provider 首字：{metadata.provider_ttft_ms ?? 0} ms</div>
      <div>缓存查询：{metadata.cache_lookup_ms ?? 0} ms</div>
      <div>应用开销：{metadata.app_overhead_ms ?? 0} ms</div>
      <div className="flex items-center gap-2"><Database size={13} />Token：{metadata.total_tokens?.toLocaleString() ?? 0}</div>
      <div>逻辑路由：{metadata.routing_decision || '自动'}</div>
      <div>响应来源：{metadata.response_source || 'provider'}</div>
      <div>Agent 迭代：{metadata.agent_iterations ?? 0}</div>
      <div>预估成本：${metadata.estimated_cost_usd?.toFixed(6) ?? '0.000000'}</div>
    </div> : null}
  </div>;
}
