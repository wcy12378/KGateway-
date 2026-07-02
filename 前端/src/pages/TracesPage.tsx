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
import { PageHeader } from '@/components/PageHeader';

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

  useEffect(() => {
    if (offset > 0 && offset >= filteredTotal) {
      const lastOffset = Math.max(0, (totalPages - 1) * TRACE_PAGE_SIZE);
      setOffset(lastOffset);
    }
  }, [filteredTotal, offset, setOffset, totalPages]);

  const goToPage = (page: number) => {
    setOffset((page - 1) * TRACE_PAGE_SIZE);
  };

  return (
    <div>
      <PageHeader title="链路追踪" description={`请求链路记录，共 ${filteredTotal} 条`} actions={<button
          onClick={fetchTraces}
          disabled={loading}
          className="button-secondary"
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          刷新
        </button>} />

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
