/**
 * Trace 页面纯逻辑工具。
 *
 * 本文件负责 trace 过滤、排序、分页和展示格式计算。它不负责 React 状态、
 * 表格渲染或后端接口请求。
 */
import type { TracesFilters } from '@/stores/traces';
import type { Department, TraceRecord } from '@/types';

export const TRACE_DEPARTMENTS: Department[] = [
  'legal',
  'hr',
  'engineering',
  'finance',
  'general',
];

export const TRACE_PAGE_SIZE = 20;

export function filterAndSortTraces(
  traces: TraceRecord[],
  filters: TracesFilters
): TraceRecord[] {
  let result = traces;

  if (filters.traceIdSearch.trim()) {
    const query = filters.traceIdSearch.trim().toLowerCase();
    result = result.filter((trace) => trace.trace_id.toLowerCase().includes(query));
  }

  if (filters.departments.length > 0) {
    const deptSet = new Set(filters.departments);
    result = result.filter((trace) => deptSet.has(trace.department));
  }

  if (filters.cacheFilter === 'hit') {
    result = result.filter((trace) => trace.cache_hit);
  } else if (filters.cacheFilter === 'miss') {
    result = result.filter((trace) => !trace.cache_hit);
  }

  if (filters.modelFilter.trim()) {
    const query = filters.modelFilter.trim().toLowerCase();
    result = result.filter((trace) => trace.model.toLowerCase().includes(query));
  }

  return [...result].sort((left, right) =>
    filters.sortDirection === 'desc'
      ? right.total_latency_ms - left.total_latency_ms
      : left.total_latency_ms - right.total_latency_ms
  );
}

export function pageTraces(
  traces: TraceRecord[],
  offset: number,
  pageSize = TRACE_PAGE_SIZE
): TraceRecord[] {
  return traces.slice(offset, offset + pageSize);
}

export function totalTracePages(total: number, pageSize = TRACE_PAGE_SIZE): number {
  return Math.max(1, Math.ceil(total / pageSize));
}

export function traceLatencyClass(ms: number): string {
  if (ms < 100) return 'text-crt-green';
  if (ms < 500) return 'text-crt-fg';
  if (ms < 1000) return 'text-yellow-500';
  return 'text-crt-red';
}

export function shortTraceModel(model: string): string {
  if (model.includes('qwen')) return 'qwen3';
  if (model.includes('deepseek') || model.includes('ds-r1')) return 'ds-r1';
  if (model.includes('claude')) return 'claude';
  return model.slice(0, 10);
}

export function traceTime(timestamp: string): string {
  return new Date(timestamp).toLocaleTimeString('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}
