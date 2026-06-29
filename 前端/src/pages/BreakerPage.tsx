/**
 * 熔断器监控页面。
 *
 * 本文件负责展示熔断器状态、统计信息和强制开关操作。它不负责实现熔断器
 * 状态机，也不直接维护后端接口路径。
 */
import { useEffect, useCallback, useRef, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { useBreakerStore } from '@/stores/breaker';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import {
  breakerActionEndpoint,
  GATEWAY_ENDPOINTS,
  type BreakerAction,
} from '@/lib/gateway';
import { requestJson } from '@/lib/http';
import { StatusAlert } from '@/components/StatusAlert';
import type { CircuitState } from '@/types';

// ---- State visuals mapping (spec §4) ----
const STATE_CONFIG: Record<
  CircuitState,
  { color: string; glow: string; label: string; desc: string }
> = {
  CLOSED: {
    color: '#32D583',
    glow: 'rgba(50,213,131,0.35)',
    label: '已关闭',
    desc: '运行正常，请求将正常转发',
  },
  OPEN: {
    color: '#F05D68',
    glow: 'rgba(240,93,104,0.35)',
    label: '已开启',
    desc: '熔断已触发，所有请求将被拒绝',
  },
  HALF_OPEN: {
    color: '#F5B942',
    glow: 'rgba(245,185,66,0.35)',
    label: '半开启',
    desc: '正在探测恢复状态，仅允许部分请求',
  },
};

type ConfirmAction = 'force-open' | 'force-close' | null;

export default function BreakerPage() {
  const stats = useBreakerStore((s) => s.stats);
  const setStats = useBreakerStore((s) => s.setStats);

  const [refreshing, setRefreshing] = useState(false);
  const [operating, setOperating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmAction, setConfirmAction] = useState<ConfirmAction>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ---- Fetch breaker stats ----
  const fetchStats = useCallback(async () => {
    setRefreshing(true);
    try {
      const data = await requestJson<NonNullable<typeof stats>>(
        GATEWAY_ENDPOINTS.circuitBreaker
      );
      setStats(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : '熔断器状态加载失败。');
    } finally {
      setRefreshing(false);
    }
  }, [setStats]);

  // ---- Polling (10s) with strict cleanup ----
  useEffect(() => {
    const initialTimer = window.setTimeout(fetchStats, 0);
    intervalRef.current = setInterval(fetchStats, 10000);
    return () => {
      if (intervalRef.current !== null) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      window.clearTimeout(initialTimer);
    };
  }, [fetchStats]);

  // ---- Force action handler ----
  const executeForce = useCallback(
    async (action: BreakerAction) => {
      setOperating(true);
      try {
        await requestJson<unknown>(breakerActionEndpoint(action), {
          method: 'POST',
        });
        // Immediate refresh after operation
        await fetchStats();
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : '熔断器操作失败。');
      } finally {
        setOperating(false);
        setConfirmAction(null);
      }
    },
    [fetchStats]
  );

  // ---- Derive state ----
  const state: CircuitState = stats?.state ?? 'CLOSED';
  const config = STATE_CONFIG[state];
  const failureCount = stats?.failure_count ?? 0;
  const threshold = stats?.failure_threshold ?? 5;
  const progressPct = Math.min((failureCount / Math.max(threshold, 1)) * 100, 100);

  // ---- Button enable/disable per spec §4 ----
  const canForceOpen = state === 'CLOSED';
  const canForceClose = state === 'OPEN';

  return (
    <div>
      {/* Header */}
      <div className="flex flex-col gap-3 mb-4 border-b border-crt-border pb-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:gap-4">
          <h1 className="font-macro text-[clamp(2rem,5vw,3.5rem)] text-crt-fg leading-none tracking-tighter">
            熔断器
          </h1>
          <span className="font-label text-crt-fg-muted">
            网关保护与恢复控制
          </span>
        </div>
        <button
          onClick={fetchStats}
          disabled={refreshing}
          className="px-3 py-1.5 border border-crt-border text-crt-fg-dim font-label tracking-widest hover:border-crt-border-strong hover:text-crt-fg transition-colors disabled:opacity-40 flex items-center gap-1.5 rounded-md"
        >
          <RefreshCw size={12} className={refreshing ? 'animate-spin' : ''} />
          刷新
        </button>
      </div>

      {error && (
        <div className="mb-4">
          <StatusAlert
            message={error}
            onRetry={fetchStats}
            onDismiss={() => setError(null)}
          />
        </div>
      )}

      {/* ===== Giant state indicator ===== */}
      <div className="border border-crt-border bg-crt-bg-elevated p-6 sm:p-8 mb-4 flex flex-col items-center gap-4 rounded-lg">
        {/* Oversized light */}
        <div
          className="w-24 h-24 rounded-2xl"
          style={{
            backgroundColor: config.color,
            boxShadow: `0 0 40px ${config.glow}, 0 0 80px ${config.glow}`,
          }}
        />
        {/* State label */}
        <div className="text-center">
          <div
            className="font-macro text-[clamp(2rem,6vw,4rem)] leading-none tracking-tighter"
            style={{ color: config.color }}
          >
            {config.label}
          </div>
          <div className="font-label text-crt-fg-muted mt-2 tracking-[0.12em]">
            {config.desc}
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex flex-col gap-3 mt-2 sm:flex-row">
          <button
            disabled={!canForceOpen || operating}
            onClick={() => setConfirmAction('force-open')}
            className="px-5 py-2 border border-crt-border font-label tracking-widest transition-colors disabled:opacity-20 disabled:cursor-not-allowed enabled:hover:border-crt-red enabled:hover:text-crt-red text-crt-fg-dim rounded-md"
          >
            强制开启熔断
          </button>
          <button
            disabled={!canForceClose || operating}
            onClick={() => setConfirmAction('force-close')}
            className="px-5 py-2 border border-crt-border font-label tracking-widest transition-colors disabled:opacity-20 disabled:cursor-not-allowed enabled:hover:border-crt-green enabled:hover:text-crt-green text-crt-fg-dim rounded-md"
          >
            强制关闭熔断
          </button>
        </div>
      </div>

      {/* ===== Failure progress bar ===== */}
      <div className="border border-crt-border bg-crt-bg-elevated p-4 mb-4 rounded-lg">
        <div className="flex items-center justify-between mb-2">
          <span className="font-label text-crt-fg-muted tracking-[0.12em]">
            当前失败次数
          </span>
          <span className="font-mono text-[11px] text-crt-fg-dim">
            {failureCount} / {threshold}
          </span>
        </div>
        <div className="h-3 bg-crt-bg w-full rounded-full overflow-hidden">
          <div
            className="h-full transition-all duration-300"
            style={{
              width: `${progressPct}%`,
              backgroundColor:
                progressPct >= 80
                  ? '#F05D68'
                  : progressPct >= 50
                  ? '#F5B942'
                  : '#32D583',
            }}
          />
        </div>
      </div>

      {/* ===== Stats grid ===== */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <div className="bg-crt-bg-elevated border border-crt-border p-5 rounded-lg">
          <div className="font-label text-crt-fg-muted tracking-[0.12em] mb-2">
            请求总数
          </div>
          <div className="font-macro text-[clamp(1.5rem,3vw,2.5rem)] text-crt-fg leading-none">
            {stats?.total_requests.toLocaleString() ?? '—'}
          </div>
        </div>
        <div className="bg-crt-bg-elevated border border-crt-border p-5 rounded-lg">
          <div className="font-label text-crt-fg-muted tracking-[0.12em] mb-2">
            失败总数
          </div>
          <div className="font-macro text-[clamp(1.5rem,3vw,2.5rem)] text-crt-red leading-none">
            {stats?.total_failures.toLocaleString() ?? '—'}
          </div>
        </div>
        <div className="bg-crt-bg-elevated border border-crt-border p-5 rounded-lg">
          <div className="font-label text-crt-fg-muted tracking-[0.12em] mb-2">
            拒绝总数
          </div>
          <div className="font-macro text-[clamp(1.5rem,3vw,2.5rem)] text-crt-red leading-none">
            {stats?.total_rejected.toLocaleString() ?? '—'}
          </div>
        </div>
      </div>

      {/* ===== Config footer ===== */}
      <div className="mt-4 flex flex-wrap gap-4 sm:gap-8 font-label text-crt-fg-muted tracking-wider">
        <span>恢复等待：{stats?.recovery_timeout ?? 60} 秒</span>
        <span>失败阈值：{threshold}</span>
        <span>实例名称：{stats?.name ?? '—'}</span>
      </div>

      {/* ===== Confirm dialogs ===== */}
      <ConfirmDialog
        open={confirmAction === 'force-open'}
        title="确认强制开启熔断"
        message="开启后，所有进入网关的请求都会立即被拒绝。请确认当前确实需要停止请求转发。"
        confirmLabel="确认开启"
        onConfirm={() => executeForce('force-open')}
        onCancel={() => setConfirmAction(null)}
      />
      <ConfirmDialog
        open={confirmAction === 'force-close'}
        title="确认强制关闭熔断"
        message="关闭后，网关会立即恢复请求转发。请确认下游服务已经恢复并具备承载能力。"
        confirmLabel="确认关闭"
        onConfirm={() => executeForce('force-close')}
        onCancel={() => setConfirmAction(null)}
      />
    </div>
  );
}
