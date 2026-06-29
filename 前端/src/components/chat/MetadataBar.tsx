/**
 * 聊天消息元数据展示条。
 *
 * 本文件负责把 SSE metadata 帧中的模型、trace、token 和延迟信息展示给用户。
 * 它不负责解析原始 SSE payload 或拉取 trace 详情。
 */
import type { SSEEvent } from '@/types';

interface MetadataBarProps {
  metadata: SSEEvent;
}

export function MetadataBar({ metadata }: MetadataBarProps) {
  // Zero-trust: every field access is guarded against undefined/null
  const m = metadata ?? {};

  const items = [
    typeof m.cache_hit === 'boolean' && {
      label: m.cache_hit ? '缓存命中' : '缓存未命中',
      color: m.cache_hit ? 'text-crt-green' : 'text-crt-fg-muted',
    },
    m.circuit_breaker === true && {
      label: '熔断生效',
      color: 'text-crt-red',
    },
    typeof m.model === 'string' &&
      m.model.length > 0 && {
        label: m.model.toUpperCase(),
        color: 'text-crt-fg',
      },
    typeof m.ttft_ms === 'number' && {
      label: `TTFT: ${m.ttft_ms}MS`,
      color: 'text-crt-fg-dim',
    },
    typeof m.total_latency_ms === 'number' && {
      label: `总延迟：${m.total_latency_ms}MS`,
      color: 'text-crt-fg-dim',
    },
    typeof m.total_tokens === 'number' && {
      label: `Token：${m.total_tokens.toLocaleString()}`,
      color: 'text-crt-fg-dim',
    },
    typeof m.estimated_cost_usd === 'number' && {
      label: `成本：$${m.estimated_cost_usd.toFixed(6)}`,
      color: 'text-crt-fg-dim',
    },
    typeof m.trace_id === 'string' &&
      m.trace_id.length > 0 && {
        label: m.trace_id,
        color: 'text-crt-fg-dim',
        mono: true,
      },
    typeof m.routing_decision === 'string' &&
      m.routing_decision.length > 0 && {
        label: `路由：${m.routing_decision.toUpperCase()}`,
        color: 'text-crt-fg-dim',
      },
    typeof m.agent_iterations === 'number' &&
      m.agent_iterations > 0 && {
        label: `迭代：${m.agent_iterations}`,
        color: 'text-crt-fg-dim',
      },
  ].filter(Boolean) as { label: string; color: string; mono?: boolean }[];

  if (items.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2 pt-2 border-t border-crt-border">
      {items.map((item, i) => (
        <span
          key={i}
          className={`font-label text-[8px] tracking-[0.12em] ${item.color} ${
            item.mono ? 'font-mono text-[9px]' : ''
          }`}
        >
          {item.label}
        </span>
      ))}
    </div>
  );
}
