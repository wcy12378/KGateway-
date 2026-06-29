/**
 * Trace 详情面板组件。
 *
 * 本文件负责展示单条 trace 的时间线、元数据和原始 JSON。它不负责拉取 trace
 * 列表、执行过滤排序或维护分页状态。
 */
import { useMemo } from 'react';
import { Copy, Check, FileJson } from 'lucide-react';
import { useState } from 'react';
import type { TraceRecord, TraceSpan } from '@/types';

// ---- Span display order per spec §5 ----
const SPAN_ORDER = [
  'circuit_breaker_check',
  'cache_lookup',
  'embedding_generation',
  'vector_search',
  'bm25_search',
  'rerank',
  'agent_runtime',
] as const;

// ---- Subtle grey-scale fills to distinguish span stages ----
const SPAN_FILLS: Record<string, string> = {
  circuit_breaker_check: '#3A3A3A',
  cache_lookup: '#4A4A4A',
  embedding_generation: '#555555',
  vector_search: '#606060',
  bm25_search: '#6B6B6B',
  rerank: '#787878',
  agent_runtime: '#888888',
};

const SPAN_LABELS: Record<string, string> = {
  circuit_breaker_check: '熔断检查',
  cache_lookup: '缓存查询',
  semantic_cache_lookup: '语义缓存查询',
  embedding_generation: '向量生成',
  vector_search: '向量检索',
  bm25_search: 'BM25 检索',
  rerank: '精排',
  agent_runtime: 'Agent 执行',
};

// ---- Diagonal hattern pattern for visual differentiation ----
function spanPattern(name: string): React.CSSProperties {
  const fill = SPAN_FILLS[name] || '#555';
  // Alternate between solid fill and diagonal stripe
  const idx = SPAN_ORDER.indexOf(name as (typeof SPAN_ORDER)[number]);
  if (idx % 2 === 0) {
    return { backgroundColor: fill };
  }
  return {
    backgroundImage: `repeating-linear-gradient(
      -45deg,
      transparent,
      transparent 2px,
      rgba(255,255,255,0.06) 2px,
      rgba(255,255,255,0.06) 4px
    )`,
    backgroundColor: fill,
  };
}

interface TraceDetailPanelProps {
  trace: TraceRecord;
}

export function TraceDetailPanel({ trace }: TraceDetailPanelProps) {
  const [copied, setCopied] = useState(false);
  const [showJson, setShowJson] = useState(false);

  const totalMs = trace.total_latency_ms || 1; // avoid /0

  // Sort spans by SPAN_ORDER, then append any unknowns
  const sortedSpans = useMemo(() => {
    const ordered: TraceSpan[] = [];
    const seen = new Set<string>();
    for (const name of SPAN_ORDER) {
      const span = trace.spans.find((s) => s.name === name);
      if (span) {
        ordered.push(span);
        seen.add(name);
      }
    }
    // Append any unknown spans
    for (const span of trace.spans) {
      if (!seen.has(span.name)) ordered.push(span);
    }
    return ordered;
  }, [trace.spans]);

  const handleCopyTraceId = () => {
    navigator.clipboard.writeText(trace.trace_id);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  // ---- Metadata fields (all 11) ----
  const metadataFields = [
    { label: 'Trace ID', value: trace.trace_id },
    { label: '时间戳', value: trace.timestamp },
    { label: '模型', value: trace.model },
    {
      label: '缓存',
      value: trace.cache_hit ? '命中' : '未命中',
      accent: trace.cache_hit ? 'green' : 'dim',
    },
    {
      label: '熔断器',
      value: trace.circuit_breaker ? '生效' : '未生效',
      accent: trace.circuit_breaker ? 'red' : 'dim',
    },
    { label: 'TTFT', value: `${trace.ttft_ms}ms` },
    { label: '总延迟', value: `${trace.total_latency_ms}ms` },
    { label: 'Token', value: trace.total_tokens.toLocaleString() },
    {
      label: '成本',
      value: `$${trace.estimated_cost_usd.toFixed(6)}`,
    },
    { label: '路由决策', value: trace.routing_decision },
    {
      label: 'Agent 迭代',
      value: String(trace.agent_iterations),
    },
  ];

  return (
    <div className="border-t border-crt-border bg-crt-bg p-4">
      {/* Metadata grid */}
      <div className="grid grid-cols-4 gap-px bg-crt-border mb-4">
        {metadataFields.map((f) => (
          <div key={f.label} className="bg-crt-bg-panel p-2.5">
            <div className="font-label text-[7px] text-crt-fg-muted tracking-[0.12em] mb-1">
              {f.label}
            </div>
            <div
              className={`font-mono text-[11px] break-all ${
                f.accent === 'green'
                  ? 'text-crt-green'
                  : f.accent === 'red'
                  ? 'text-crt-red'
                  : 'text-crt-fg'
              }`}
            >
              {f.value}
            </div>
          </div>
        ))}
      </div>

      {/* ===== Span waterfall (pure hand-drawn CSS) ===== */}
      <div className="mb-4">
        <div className="font-label text-[8px] text-crt-fg-muted tracking-[0.12em] mb-3">
          阶段耗时瀑布图
        </div>

        {sortedSpans.length === 0 ? (
          <div className="font-label text-[9px] text-crt-fg-muted p-3 border border-crt-border bg-crt-bg-panel">
            暂无阶段耗时数据
          </div>
        ) : (
          <div className="border border-crt-border bg-crt-bg-panel">
            {sortedSpans.map((span, i) => {
              const pct = Math.max(
                (span.duration_ms / totalMs) * 100,
                1
              );
              return (
                <div
                  key={span.name}
                  className={`flex items-stretch ${
                    i < sortedSpans.length - 1
                      ? 'border-b border-crt-border'
                      : ''
                  }`}
                >
                  {/* Label column */}
                  <div className="w-48 shrink-0 px-3 py-2 border-r border-crt-border flex flex-col justify-center">
                    <span className="font-mono text-[10px] text-crt-fg">
                      {SPAN_LABELS[span.name] ?? span.name}
                    </span>
                    <span className="font-mono text-[9px] text-crt-fg-muted mt-0.5">
                      {span.name}
                    </span>
                    {span.result && (
                      <span
                        className={`font-label text-[7px] mt-0.5 ${
                          span.result === 'HIT'
                            ? 'text-crt-green'
                            : 'text-crt-fg-muted'
                        }`}
                      >
                        {span.result === 'HIT'
                          ? '命中'
                          : span.result === 'MISS'
                          ? '未命中'
                          : span.result}
                      </span>
                    )}
                  </div>

                  {/* Bar column */}
                  <div className="flex-1 px-3 py-2 flex items-center gap-3">
                    <div className="flex-1 h-4 bg-crt-bg flex items-center">
                      <div
                        className="h-full"
                        style={{
                          width: `${pct}%`,
                          ...spanPattern(span.name),
                        }}
                      />
                    </div>
                    <span className="font-mono text-[10px] text-crt-fg-dim tabular-nums w-14 text-right shrink-0">
                      {span.duration_ms}ms
                    </span>
                    <span className="font-label text-[7px] text-crt-fg-muted w-10 text-right shrink-0">
                      {pct.toFixed(1)}%
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Action buttons */}
      <div className="flex gap-2">
        <button
          onClick={handleCopyTraceId}
          className="px-3 py-1.5 border border-crt-border text-crt-fg-dim font-label text-[8px] tracking-widest hover:border-crt-fg hover:text-crt-fg transition-colors flex items-center gap-1.5"
        >
          {copied ? <Check size={11} /> : <Copy size={11} />}
          {copied ? '已复制' : '复制 Trace ID'}
        </button>
        <button
          onClick={() => setShowJson(!showJson)}
          className="px-3 py-1.5 border border-crt-border text-crt-fg-dim font-label text-[8px] tracking-widest hover:border-crt-fg hover:text-crt-fg transition-colors flex items-center gap-1.5"
        >
          <FileJson size={11} />
          {showJson ? '隐藏 JSON' : '查看原始 JSON'}
        </button>
      </div>

      {/* Raw JSON viewer */}
      {showJson && (
        <pre className="mt-3 p-3 bg-crt-bg border border-crt-border text-[10px] font-mono text-crt-fg-dim overflow-x-auto leading-relaxed">
          {JSON.stringify(trace, null, 2)}
        </pre>
      )}
    </div>
  );
}
