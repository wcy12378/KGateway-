/**
 * Trace 表格组件。
 *
 * 本文件负责渲染 trace 行、展开状态和详情面板。它不负责拉取 trace 列表、
 * 执行过滤排序或维护分页。
 */
import { Fragment } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import {
  shortTraceModel,
  traceLatencyClass,
  traceTime,
} from '@/lib/traces';
import type { TraceRecord } from '@/types';
import { TraceDetailPanel } from './TraceDetailPanel';

interface TraceTableProps {
  traces: TraceRecord[];
  expandedTraceId: string | null;
  loading: boolean;
  onToggleExpanded: (traceId: string | null) => void;
}

export function TraceTable({
  traces,
  expandedTraceId,
  loading,
  onToggleExpanded,
}: TraceTableProps) {
  return (
    <div className="border border-crt-border bg-crt-bg-elevated rounded-lg overflow-hidden">
      <div className="overflow-x-auto">
      <table className="w-full min-w-[920px] text-[12px] font-mono">
        <thead>
          <tr className="border-b border-crt-border text-crt-fg-muted">
            <th className="text-left p-2 font-label text-[10px] tracking-wider w-8" />
            <th className="text-left p-2 font-label text-[10px] tracking-wider">
              Trace ID
            </th>
            <th className="text-left p-2 font-label text-[10px] tracking-wider w-[80px]">
              时间
            </th>
            <th className="text-left p-2 font-label text-[10px] tracking-wider w-[80px]">
              延迟
            </th>
            <th className="text-left p-2 font-label text-[10px] tracking-wider w-[60px]">
              缓存
            </th>
            <th className="text-left p-2 font-label text-[10px] tracking-wider w-[70px]">
              模型
            </th>
            <th className="text-left p-2 font-label text-[10px] tracking-wider w-[70px]">
              Token
            </th>
            <th className="text-left p-2 font-label text-[10px] tracking-wider w-[90px]">
              成本
            </th>
            <th className="text-left p-2 font-label text-[10px] tracking-wider w-[80px]">
              用户
            </th>
          </tr>
        </thead>
        <tbody>
          {traces.length === 0 ? (
            <tr>
              <td
                colSpan={9}
                className="p-6 text-center font-label text-crt-fg-muted"
              >
                {loading ? '正在加载链路记录...' : '暂无匹配的链路记录。'}
              </td>
            </tr>
          ) : (
            traces.map((trace) => {
              const isExpanded = expandedTraceId === trace.trace_id;
              return (
                <Fragment key={trace.trace_id}>
                  <tr
                    onClick={() =>
                      onToggleExpanded(isExpanded ? null : trace.trace_id)
                    }
                    className={`border-b border-crt-border cursor-pointer transition-colors ${
                      isExpanded ? 'bg-crt-bg-panel' : 'hover:bg-crt-bg-panel'
                    }`}
                  >
                    <td className="p-2 text-crt-fg-dim">
                      {isExpanded ? (
                        <ChevronDown size={12} />
                      ) : (
                        <ChevronRight size={12} />
                      )}
                    </td>
                    <td className="p-2 text-crt-fg font-mono text-[10px]">
                      {trace.trace_id}
                    </td>
                    <td className="p-2 text-crt-fg-dim tabular-nums">
                      {traceTime(trace.timestamp)}
                    </td>
                    <td
                      className={`p-2 tabular-nums ${traceLatencyClass(
                        trace.total_latency_ms
                      )}`}
                    >
                      {trace.total_latency_ms}ms
                    </td>
                    <td className="p-2">
                      <span
                        className={`font-label text-[9px] ${
                          trace.cache_hit ? 'text-crt-green' : 'text-crt-fg-muted'
                        }`}
                      >
                        {trace.cache_hit ? '命中' : '未命中'}
                      </span>
                    </td>
                    <td className="p-2 text-crt-fg-dim text-[10px]">
                      {shortTraceModel(trace.model)}
                    </td>
                    <td className="p-2 text-crt-fg-dim tabular-nums">
                      {trace.total_tokens.toLocaleString()}
                    </td>
                    <td className="p-2 text-crt-fg-dim tabular-nums text-[10px]">
                      ${trace.estimated_cost_usd.toFixed(6)}
                    </td>
                    <td className="p-2 text-crt-fg-dim text-[10px]">
                      {trace.user_id.length > 10
                        ? `${trace.user_id.slice(0, 10)}...`
                        : trace.user_id}
                    </td>
                  </tr>

                  {isExpanded && (
                    <tr>
                      <td colSpan={9} className="p-0">
                        <TraceDetailPanel trace={trace} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })
          )}
        </tbody>
      </table>
      </div>
    </div>
  );
}
