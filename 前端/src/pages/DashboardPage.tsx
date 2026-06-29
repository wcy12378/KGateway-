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
import { StatusAlert } from '@/components/StatusAlert';
import type { RecentRequest } from '@/components/dashboard/RecentRequestsTable';
import type { MetricsSnapshot, TraceRecord } from '@/types';

interface GatewayMetricsResponse {
  metrics: MetricsSnapshot;
}

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

  // ---- Fetch metrics ----
  const fetchMetrics = useCallback(async () => {
    setRefreshing(true);
    try {
      const [metricsResponse, traces] = await Promise.all([
        requestJson<GatewayMetricsResponse>(GATEWAY_ENDPOINTS.metrics),
        requestJson<{ traces: TraceRecord[] }>(tracesEndpoint(20, 0)),
      ]);
      setSnapshot(metricsResponse.metrics);
      setRecentRequests(traces.traces.map(toRecentRequest));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : '指标数据加载失败。');
    } finally {
      setRefreshing(false);
    }
  }, [setSnapshot]);

  // ---- Polling with strict cleanup ----
  useEffect(() => {
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
    };
  }, [refreshInterval, fetchMetrics]);

  // ---- Memoize histogram distribution ----
  const distribution = useMemo(
    () => snapshot?.latency_distribution ?? null,
    [snapshot]
  );

  return (
    <div>
      {/* Header row */}
      <div className="flex flex-col gap-3 mb-4 border-b border-crt-border pb-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:gap-4">
          <h1 className="font-macro text-[clamp(2rem,5vw,3.5rem)] text-crt-fg leading-none tracking-tighter">
            运行指标
          </h1>
          <span className="font-label text-crt-fg-muted">
            网关监控看板
          </span>
        </div>

        {/* 刷新控制 */}
        <div className="flex flex-wrap items-center gap-3">
          <span className="font-label text-crt-fg-muted">
            自动刷新
          </span>
          <select
            value={refreshInterval}
            onChange={(e) => setRefreshInterval(Number(e.target.value))}
            className="bg-crt-bg-elevated border border-crt-border text-crt-fg text-[12px] font-mono px-2 py-1.5 focus:outline-none focus:border-crt-border-strong"
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
            className="px-3 py-1.5 border border-crt-border text-crt-fg-dim font-label tracking-widest hover:border-crt-border-strong hover:text-crt-fg transition-colors disabled:opacity-40 flex items-center gap-1.5 rounded-md"
          >
            <RefreshCw
              size={12}
              className={refreshing ? 'animate-spin' : ''}
            />
            刷新
          </button>
        </div>
      </div>

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
