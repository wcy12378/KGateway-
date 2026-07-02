import { useCallback, useEffect, useState } from 'react';
import { Braces, FileText, RefreshCw } from 'lucide-react';
import { PageHeader } from '@/components/PageHeader';
import { StatusAlert } from '@/components/StatusAlert';
import { GATEWAY_ENDPOINTS } from '@/lib/gateway';
import { requestJson } from '@/lib/http';
import type { PromptSummary } from '@/types';

export default function PromptsPage() {
  const [items, setItems] = useState<PromptSummary[]>([]); const [loading, setLoading] = useState(true); const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => { setLoading(true); try { const data = await requestJson<{ prompts: PromptSummary[] }>(GATEWAY_ENDPOINTS.prompts); setItems(data.prompts); setError(null); } catch (err) { setError(err instanceof Error ? err.message : 'Prompt 模板加载失败'); } finally { setLoading(false); } }, []);
  useEffect(() => { const timer = window.setTimeout(load, 0); return () => window.clearTimeout(timer); }, [load]);
  return <div><PageHeader title="Prompt 模板" description="查看当前生效版本、变量契约与内容指纹" actions={<button onClick={load} className="button-secondary" disabled={loading}><RefreshCw size={14} className={loading ? 'animate-spin' : ''} />刷新</button>} />
    {error ? <div className="mb-4"><StatusAlert message={error} onRetry={load} onDismiss={() => setError(null)} /></div> : null}
    <div className="surface-panel overflow-hidden"><div className="overflow-x-auto"><table><thead><tr className="border-b border-crt-border bg-crt-bg"><th className="px-4 py-3">模板</th><th className="px-4 py-3">活动版本</th><th className="px-4 py-3">全部版本</th><th className="px-4 py-3">变量</th><th className="px-4 py-3">内容指纹</th></tr></thead><tbody>
      {loading ? Array.from({ length: 4 }).map((_, i) => <tr key={i} className="border-b border-crt-border"><td colSpan={5} className="px-4 py-4"><div className="skeleton h-5" /></td></tr>) : items.map((item) => <tr key={item.name} className="border-b border-crt-border last:border-0 hover:bg-crt-bg"><td className="px-4 py-4"><div className="flex items-start gap-3"><div className="grid h-8 w-8 place-items-center rounded-lg bg-crt-bg-panel text-blue-700"><FileText size={15} /></div><div><div className="text-[12px] font-semibold text-crt-fg">{item.name}</div><div className="mt-0.5 max-w-xs text-[10px] text-crt-fg-muted">{item.description || '未提供说明'}</div></div></div></td><td className="px-4 py-4"><span className="status-badge bg-emerald-50 text-emerald-700">v{item.active_version}</span></td><td className="px-4 py-4 text-[11px]">{item.versions.map((version) => `v${version}`).join(' · ')}</td><td className="px-4 py-4"><div className="flex max-w-xs flex-wrap gap-1">{item.variables.length ? item.variables.map((name) => <span key={name} className="inline-flex items-center gap-1 rounded bg-crt-bg px-1.5 py-1 font-mono text-[9px]"><Braces size={10} />{name}</span>) : <span className="text-[10px] text-crt-fg-muted">无变量</span>}</div></td><td className="px-4 py-4 font-mono text-[10px] text-crt-fg-muted">{item.hash}</td></tr>)}
      {!loading && !items.length ? <tr><td colSpan={5} className="px-4 py-16 text-center text-[12px] text-crt-fg-muted">暂无 Prompt 模板</td></tr> : null}
    </tbody></table></div></div>
  </div>;
}
