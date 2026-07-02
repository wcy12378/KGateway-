import { useCallback, useEffect, useState } from 'react';
import { ArrowRight, CheckCircle2, LoaderCircle, Play, Workflow } from 'lucide-react';
import { PageHeader } from '@/components/PageHeader';
import { StatusAlert } from '@/components/StatusAlert';
import { GATEWAY_ENDPOINTS } from '@/lib/gateway';
import { requestJson } from '@/lib/http';
import { useChatStore } from '@/stores/chat';
import type { WorkflowRunResult, WorkflowSummary } from '@/types';

const MODE_LABELS: Record<string, string> = { sequential: '顺序执行', routing: '规则路由', parallel: '并行合成' };

export default function WorkflowsPage() {
  const [items, setItems] = useState<WorkflowSummary[]>([]);
  const [selected, setSelected] = useState('');
  const [question, setQuestion] = useState('');
  const [result, setResult] = useState<WorkflowRunResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const buildRequest = useChatStore((s) => s.buildRequest);

  const load = useCallback(async () => { setLoading(true); try { const data = await requestJson<{ workflows: WorkflowSummary[] }>(GATEWAY_ENDPOINTS.workflows); setItems(data.workflows); setSelected((current) => current || data.workflows[0]?.name || ''); setError(null); } catch (err) { setError(err instanceof Error ? err.message : '工作流加载失败'); } finally { setLoading(false); } }, []);
  useEffect(() => { const timer = window.setTimeout(load, 0); return () => window.clearTimeout(timer); }, [load]);

  const run = async () => { if (!selected || !question.trim()) return; setRunning(true); setResult(null); try { const data = await requestJson<WorkflowRunResult>(GATEWAY_ENDPOINTS.workflow, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...buildRequest(question.trim()), workflow_name: selected }), timeoutMs: 120_000 }); setResult(data); setError(null); } catch (err) { setError(err instanceof Error ? err.message : '工作流执行失败'); } finally { setRunning(false); } };
  const active = items.find((item) => item.name === selected);

  return <div><PageHeader title="Agent 工作流" description="编排多个专用 Agent，执行可观察、可复核的复杂任务" />
    {error ? <div className="mb-4"><StatusAlert message={error} onRetry={load} onDismiss={() => setError(null)} /></div> : null}
    <div className="grid gap-4 lg:grid-cols-[300px_minmax(0,1fr)]">
      <aside className="surface-panel overflow-hidden"><div className="border-b border-crt-border px-4 py-3 text-[11px] font-semibold text-crt-fg-muted">可用工作流</div>
        {loading ? <div className="space-y-3 p-4"><div className="skeleton h-16" /><div className="skeleton h-16" /></div> : items.length ? <div className="p-2">{items.map((item) => <button key={item.name} onClick={() => { setSelected(item.name); setResult(null); }} className={`mb-1 w-full rounded-lg p-3 text-left ${selected === item.name ? 'bg-crt-bg-panel' : 'hover:bg-crt-bg'}`}><div className="flex items-center gap-2"><Workflow size={15} className={selected === item.name ? 'text-blue-700' : 'text-crt-fg-muted'} /><span className="text-[12px] font-semibold">{item.name}</span></div><div className="mt-1.5 text-[10px] text-crt-fg-muted">{MODE_LABELS[item.mode] ?? item.mode} · {item.agents.length} 个 Agent</div></button>)}</div> : <div className="p-6 text-center text-[12px] text-crt-fg-muted">暂无可用工作流</div>}
      </aside>
      <section className="surface-panel min-w-0 p-4 sm:p-5">{active ? <><div className="mb-5 flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-[15px] font-semibold">{active.name}</h2><p className="mt-1 text-[11px] text-crt-fg-muted">{MODE_LABELS[active.mode] ?? active.mode}</p></div><span className="status-badge bg-emerald-50 text-emerald-700">已就绪</span></div>
        <div className="mb-5 flex flex-wrap items-center gap-2">{active.agents.map((agent, index) => <div key={agent.name} className="flex items-center gap-2"><div className="rounded-lg border border-crt-border bg-crt-bg px-3 py-2"><div className="text-[11px] font-semibold">{agent.name}</div><div className="mt-0.5 text-[9px] text-crt-fg-muted">Prompt v{agent.prompt_version ?? 'active'}</div></div>{index < active.agents.length - 1 ? <ArrowRight size={14} className="text-crt-fg-muted" /> : null}</div>)}</div>
        <label className="text-[11px] font-medium text-crt-fg-dim">任务描述<textarea className="field-control mt-1.5 min-h-28 resize-y text-[13px]" value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="描述希望工作流完成的任务…" /></label>
        <div className="mt-3 flex justify-end"><button onClick={run} disabled={running || !question.trim()} className="button-primary">{running ? <LoaderCircle size={15} className="animate-spin" /> : <Play size={14} />}{running ? '执行中' : '运行工作流'}</button></div>
        {result ? <div className="mt-6 border-t border-crt-border pt-5"><div className="mb-3 flex items-center gap-2"><CheckCircle2 size={16} className="text-crt-green" /><h3 className="text-[13px] font-semibold">执行结果</h3><span className="ml-auto text-[10px] text-crt-fg-muted">{Math.round(result.total_duration_ms)} ms · {result.total_tokens} Token</span></div><div className="rounded-lg bg-crt-bg p-4 text-[13px] leading-6 whitespace-pre-wrap">{result.final_answer}</div><div className="mt-3 space-y-2">{result.steps.map((step) => <details key={`${step.agent_name}-${step.duration_ms}`} className="rounded-lg border border-crt-border px-3 py-2"><summary className="cursor-pointer text-[11px] font-medium">{step.agent_name}<span className="ml-2 text-crt-fg-muted">{step.status} · {Math.round(step.duration_ms)} ms</span></summary><div className="mt-2 text-[11px] leading-5 text-crt-fg-dim">{step.error || step.answer || '无输出'}</div></details>)}</div></div> : null}
      </> : <div className="grid min-h-72 place-items-center text-[12px] text-crt-fg-muted">选择一个工作流开始</div>}</section>
    </div>
  </div>;
}
