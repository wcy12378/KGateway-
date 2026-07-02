import { useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, CheckCircle2, RefreshCw, ShieldCheck } from 'lucide-react';
import { PageHeader } from '@/components/PageHeader';
import { StatusAlert } from '@/components/StatusAlert';
import { GATEWAY_ENDPOINTS, normalizeCircuitState } from '@/lib/gateway';
import { requestJson } from '@/lib/http';
import { createLatestRequestController } from '@/lib/latestRequest';
import { useBreakerStore } from '@/stores/breaker';
import type { CircuitState } from '@/types';

const STATES: Record<CircuitState, { label: string; description: string; className: string }> = {
  CLOSED: { label: '运行正常', description: '熔断器关闭，请求正常转发', className: 'bg-emerald-50 text-emerald-700' },
  OPEN: { label: '保护生效', description: '熔断器开启，请求将被拒绝', className: 'bg-red-50 text-red-700' },
  HALF_OPEN: { label: '恢复探测', description: '仅允许部分请求验证下游状态', className: 'bg-amber-50 text-amber-700' },
};
const UNKNOWN_STATE = { label: '状态未知', description: '后端返回了无法识别的熔断器状态', className: 'bg-slate-100 text-slate-700' };

export default function BreakerPage() {
  const stats = useBreakerStore((s) => s.stats); const setStats = useBreakerStore((s) => s.setStats);
  const [loading, setLoading] = useState(false); const [error, setError] = useState<string | null>(null);
  const requestControllerRef = useRef(createLatestRequestController());
  const load = useCallback(async () => { const activeRequest = requestControllerRef.current.next(); setLoading(true); try { const nextStats = await requestJson<NonNullable<typeof stats>>(GATEWAY_ENDPOINTS.circuitBreaker, { signal: activeRequest.signal }); if (!activeRequest.isCurrent()) return; const normalizedState = normalizeCircuitState(nextStats.state); if (!normalizedState || normalizedState === 'N/A') throw new Error('熔断器返回未知状态'); setStats({ ...nextStats, state: normalizedState }); setError(null); } catch (err) { if (err instanceof DOMException && err.name === 'AbortError') return; if (activeRequest.isCurrent()) setError(err instanceof Error ? err.message : '熔断器状态加载失败'); } finally { if (activeRequest.isCurrent()) setLoading(false); } }, [setStats]);
  useEffect(() => { const requestController = requestControllerRef.current; const initial = window.setTimeout(load, 0); const timer = window.setInterval(load, 10_000); return () => { window.clearTimeout(initial); window.clearInterval(timer); requestController.abort(); }; }, [load]);
  const state = normalizeCircuitState(stats?.state) ?? 'N/A'; const stateInfo = state === 'N/A' ? UNKNOWN_STATE : STATES[state]; const failures = stats?.failure_count ?? 0; const threshold = Math.max(stats?.failure_threshold ?? 5, 1); const progress = Math.min(100, failures / threshold * 100);
  return <div><PageHeader title="熔断器" description="监控下游健康状态并控制网关保护策略" actions={<button onClick={load} disabled={loading} className="button-secondary"><RefreshCw size={14} className={loading ? 'animate-spin' : ''} />刷新</button>} />
    {error ? <div className="mb-4"><StatusAlert message={error} onRetry={load} onDismiss={() => setError(null)} /></div> : null}
    <section className="surface-panel mb-4 p-5"><div className="flex flex-col gap-5 sm:flex-row sm:items-center"><div className={`grid h-12 w-12 shrink-0 place-items-center rounded-[10px] ${stateInfo.className}`}>{state === 'CLOSED' ? <ShieldCheck size={22} /> : <AlertTriangle size={22} />}</div><div className="flex-1"><div className="flex flex-wrap items-center gap-2"><h2 className="text-[16px] font-semibold">{stateInfo.label}</h2><span className={`status-badge ${stateInfo.className}`}>{state}</span></div><p className="mt-1 text-[12px] text-crt-fg-dim">{stateInfo.description}</p></div><div className="flex gap-2" title="管理操作仅允许服务端 API Key 调用"><button disabled className="button-danger">强制开启</button><button disabled className="button-secondary">恢复转发</button></div></div><p className="mt-3 text-[10px] text-crt-fg-muted">浏览器控制台仅提供只读监控；熔断器管理操作需通过受控服务端调用。</p></section>
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(300px,.6fr)]"><section className="surface-panel p-5"><div className="mb-4 flex items-center justify-between"><div><h3 className="text-[13px] font-semibold">失败阈值</h3><p className="mt-1 text-[10px] text-crt-fg-muted">连续失败达到阈值后进入保护状态</p></div><span className="font-mono text-[12px]">{failures} / {threshold}</span></div><div className="h-2 overflow-hidden rounded-full bg-slate-100"><div className={`h-full rounded-full ${progress >= 80 ? 'bg-red-500' : progress >= 50 ? 'bg-amber-500' : 'bg-emerald-600'}`} style={{ width: `${progress}%` }} /></div><div className="mt-5 grid grid-cols-2 gap-3 text-[11px] sm:grid-cols-4"><div><div className="text-crt-fg-muted">恢复等待</div><div className="mt-1 font-semibold">{stats?.recovery_timeout ?? 60} 秒</div></div><div><div className="text-crt-fg-muted">实例名称</div><div className="mt-1 truncate font-semibold">{stats?.name ?? '—'}</div></div><div><div className="text-crt-fg-muted">失败率</div><div className="mt-1 font-semibold">{stats?.total_requests ? `${(stats.total_failures / stats.total_requests * 100).toFixed(1)}%` : '0%'}</div></div><div><div className="text-crt-fg-muted">拒绝率</div><div className="mt-1 font-semibold">{stats?.total_requests ? `${(stats.total_rejected / stats.total_requests * 100).toFixed(1)}%` : '0%'}</div></div></div></section>
      <section className="surface-panel divide-y divide-crt-border">{[{ label: '请求总数', value: stats?.total_requests ?? 0, tone: '' }, { label: '失败总数', value: stats?.total_failures ?? 0, tone: 'text-crt-red' }, { label: '拒绝总数', value: stats?.total_rejected ?? 0, tone: 'text-crt-red' }].map((item) => <div key={item.label} className="flex items-center justify-between px-5 py-4"><span className="text-[11px] text-crt-fg-muted">{item.label}</span><span className={`text-[18px] font-semibold tabular-nums ${item.tone}`}>{item.value.toLocaleString()}</span></div>)}</section></div>
    <div className="mt-4 flex items-center gap-2 text-[10px] text-crt-fg-muted"><CheckCircle2 size={13} className="text-crt-green" />状态每 10 秒自动更新</div>
  </div>;
}
