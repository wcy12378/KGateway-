/**
 * Trace 历史页面。
 *
 * 本文件负责拉取 trace 列表、连接 trace store，并组装过滤、表格和分页组件。
 * 它不负责 trace 过滤算法、表格行渲染或网关接口路径定义。
 */
import { useEffect, useCallback, useRef, useState, useMemo } from 'react';
import { RefreshCw } from 'lucide-react';
import { TraceFilters } from '@/components/traces/TraceFilters';
import { TracePagination } from '@/components/traces/TracePagination';
import { TraceTable } from '@/components/traces/TraceTable';
import {
  filterAndSortTraces,
  pageTraces,
  totalTracePages,
  TRACE_PAGE_SIZE,
} from '@/lib/traces';
import { tracesEndpoint } from '@/lib/gateway';
import { requestJson } from '@/lib/http';
import { useTracesStore } from '@/stores/traces';
import { StatusAlert } from '@/components/StatusAlert';
import type { TraceRecord } from '@/types';

export default function TracesPage() {
  const offset = useTracesStore((state) => state.offset);
  const filters = useTracesStore((state) => state.filters);
  const expandedTraceId = useTracesStore((state) => state.expandedTraceId);
  const setOffset = useTracesStore((state) => state.setOffset);
  const setFilters = useTracesStore((state) => state.setFilters);
  const setExpandedTraceId = useTracesStore((state) => state.setExpandedTraceId);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [allTraces, setAllTraces] = useState<TraceRecord[]>([]);
  const abortRef = useRef<AbortController | null>(null);

  const fetchTraces = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    try {
      const data = await requestJson<{ traces: TraceRecord[] }>(tracesEndpoint(200, 0), {
        signal: controller.signal,
      });
      setAllTraces(data.traces);
      setError(null);
    } catch (error: unknown) {
      if (error instanceof DOMException && error.name === 'AbortError') return;
      setError(error instanceof Error ? error.message : 'Trace 数据加载失败。');
    } finally {
      if (abortRef.current === controller) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    const initialTimer = window.setTimeout(fetchTraces, 0);
    return () => {
      window.clearTimeout(initialTimer);
      abortRef.current?.abort();
    };
  }, [fetchTraces]);

  const filtered = useMemo(
    () => filterAndSortTraces(allTraces, filters),
    [allTraces, filters]
  );
  const filteredTotal = filtered.length;
  const totalPages = totalTracePages(filteredTotal);
  const currentPage = Math.floor(offset / TRACE_PAGE_SIZE) + 1;
  const visibleTraces = pageTraces(filtered, offset);

  const goToPage = (page: number) => {
    setOffset((page - 1) * TRACE_PAGE_SIZE);
  };

  return (
    <div>
      <div className="flex flex-col gap-3 mb-4 border-b border-crt-border pb-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:gap-4">
          <h1 className="font-macro text-[clamp(2rem,5vw,3.5rem)] text-crt-fg leading-none tracking-tighter">
            链路追踪
          </h1>
          <span className="font-label text-crt-fg-muted">
            请求链路记录 / 共 {filteredTotal} 条
          </span>
        </div>
        <button
          onClick={fetchTraces}
          disabled={loading}
          className="px-3 py-1.5 border border-crt-border text-crt-fg-dim font-label tracking-widest hover:border-crt-border-strong hover:text-crt-fg transition-colors disabled:opacity-40 flex items-center gap-1.5 rounded-md"
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          刷新
        </button>
      </div>

      {error && (
        <div className="mb-4">
          <StatusAlert
            message={error}
            onRetry={fetchTraces}
            onDismiss={() => setError(null)}
          />
        </div>
      )}

      <TraceFilters filters={filters} onChange={setFilters} />

      <TraceTable
        traces={visibleTraces}
        expandedTraceId={expandedTraceId}
        loading={loading}
        onToggleExpanded={setExpandedTraceId}
      />

      <TracePagination
        offset={offset}
        pageSize={TRACE_PAGE_SIZE}
        total={filteredTotal}
        currentPage={currentPage}
        totalPages={totalPages}
        onPageChange={goToPage}
      />
    </div>
  );
}
