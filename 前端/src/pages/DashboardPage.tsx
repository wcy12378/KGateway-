/**
 * 指标看板页面。
 *
 * 本文件负责拉取 metrics 和最近 trace，并组合指标卡、延迟图和最近请求表格。
 * 它不负责后端指标聚合、trace 采集或接口路径定义。
 */
import { useEffect, useCallback, useRef, useState, useMemo } from 'react';
import { RefreshCw } from 'lucide-react';
import { useMetricsStore } from '@/stores/metrics';
import { MetricCards } from '@/components/dashboard/MetricCards';
import { LatencyHistogram } from '@/components/dashboard/LatencyHistogram';
import { RecentRequestsTable } from '@/components/dashboard/RecentRequestsTable';
import { GATEWAY_ENDPOINTS, tracesEndpoint } from '@/lib/gateway';
import { requestJson } from '@/lib/http';
import { createLatestRequestController } from '@/lib/latestRequest';
import { StatusAlert } from '@/components/StatusAlert';
import type { RecentRequest } from '@/components/dashboard/RecentRequestsTable';
import type { MetricsSnapshot, TraceRecord } from '@/types';
import { PageHeader } from '@/components/PageHeader';

// ---- Interval options ----
const INTERVALS = [
  { label: '关闭', value: 0 },
  { label: '5s', value: 5000 },
  { label: '10s', value: 10000 },
  { label: '30s', value: 30000 },
  { label: '60s', value: 60000 },
] as const;

// ---- Transform TraceRecord → RecentRequest ----
function toRecentRequest(t: TraceRecord): RecentRequest {
  const d = new Date(t.timestamp);
  const time = d.toLocaleTimeString('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
  return {
    traceId: t.trace_id,
    time,
    user: t.user_id,
    dept: t.department,
    cache: t.cache_hit,
    latency: `${t.total_latency_ms}ms`,
  };
}

export default function DashboardPage() {
  const snapshot = useMetricsStore((s) => s.snapshot);
  const refreshInterval = useMetricsStore((s) => s.refreshInterval);
  const setSnapshot = useMetricsStore((s) => s.setSnapshot);
  const setRefreshInterval = useMetricsStore((s) => s.setRefreshInterval);

  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recentRequests, setRecentRequests] = useState<RecentRequest[]>([]);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const requestControllerRef = useRef(createLatestRequestController());

  // ---- Fetch metrics ----
  const fetchMetrics = useCallback(async () => {
    const activeRequest = requestControllerRef.current.next();
    setRefreshing(true);
    try {
      const [metricsResponse, traces] = await Promise.all([
        requestJson<MetricsSnapshot>(GATEWAY_ENDPOINTS.metrics, { signal: activeRequest.signal }),
        requestJson<{ traces: TraceRecord[] }>(tracesEndpoint(20, 0), { signal: activeRequest.signal }),
      ]);
      if (!activeRequest.isCurrent()) return;
      setSnapshot(metricsResponse);
      setRecentRequests(traces.traces.map(toRecentRequest));
      setError(null);
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      if (!activeRequest.isCurrent()) return;
      setError(err instanceof Error ? err.message : '指标数据加载失败。');
    } finally {
      if (activeRequest.isCurrent()) setRefreshing(false);
    }
  }, [setSnapshot]);

  // ---- Polling with strict cleanup ----
  useEffect(() => {
    const requestController = requestControllerRef.current;
    const initialTimer = window.setTimeout(fetchMetrics, 0);

    // Set up interval
    if (refreshInterval > 0) {
      intervalRef.current = setInterval(fetchMetrics, refreshInterval);
    }

    // Cleanup: MUST clear on unmount or interval change
    return () => {
      if (intervalRef.current !== null) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      window.clearTimeout(initialTimer);
      requestController.abort();
    };
  }, [refreshInterval, fetchMetrics]);

  // ---- Memoize histogram distribution ----
  const distribution = useMemo(
    () => snapshot?.latency_distribution ?? null,
    [snapshot]
  );

  return (
    <div>
      <PageHeader title="运行指标" description="网关吞吐、缓存效率、模型成本与延迟分布" actions={
        <>
          <span className="font-label text-crt-fg-muted">
            自动刷新
          </span>
          <select
            value={refreshInterval}
            onChange={(e) => setRefreshInterval(Number(e.target.value))}
            className="field-control h-[34px] w-20 py-1 text-[11px]"
          >
            {INTERVALS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <button
            onClick={fetchMetrics}
            disabled={refreshing}
            className="button-secondary"
          >
            <RefreshCw
              size={12}
              className={refreshing ? 'animate-spin' : ''}
            />
            刷新
          </button>
        </>
      } />

      {error && (
        <div className="mb-4">
          <StatusAlert
            message={error}
            onRetry={fetchMetrics}
            onDismiss={() => setError(null)}
          />
        </div>
      )}

      {/* 4 metric cards */}
      <MetricCards snapshot={snapshot} />

      {/* Latency histogram */}
      <div className="mt-4">
        <LatencyHistogram distribution={distribution} />
      </div>

      {/* Recent requests table */}
      <div className="mt-4">
        <RecentRequestsTable requests={recentRequests} />
      </div>
    </div>
  );
}
