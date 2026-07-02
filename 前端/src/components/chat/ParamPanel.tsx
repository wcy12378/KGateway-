import { X } from 'lucide-react';
import { useChatStore } from '@/stores/chat';
import type { Department } from '@/types';
import { DEV_AUTH_ENABLED } from '@/lib/http';

const DEPARTMENTS: { value: Department; label: string }[] = [
  { value: 'general', label: '通用' }, { value: 'legal', label: '法务' }, { value: 'hr', label: '人力' },
  { value: 'engineering', label: '工程' }, { value: 'finance', label: '财务' },
];

export function ParamPanel({ onClose }: { onClose?: () => void }) {
  const params = useChatStore((s) => s.gatewayParams);
  const setParams = useChatStore((s) => s.setGatewayParams);
  const sessionId = useChatStore((s) => s.currentSessionId);
  return <aside className="fixed inset-y-0 right-0 z-40 flex w-[320px] flex-col border-l border-crt-border bg-white shadow-xl lg:static lg:z-auto lg:w-72 lg:rounded-[10px] lg:border lg:shadow-none">
    <header className="flex h-14 items-center border-b border-crt-border px-4"><div><h2 className="text-[13px] font-semibold">请求设置</h2><p className="text-[10px] text-crt-fg-muted">下一次对话生效</p></div><button onClick={onClose} className="icon-button ml-auto" aria-label="关闭设置"><X size={16} /></button></header>
    <div className="flex-1 space-y-4 overflow-y-auto p-4">
      {DEV_AUTH_ENABLED ? <p className="rounded-lg bg-blue-50 p-3 text-[10px] leading-5 text-blue-800">开发认证已启用，身份由当前 JWT 决定。</p> : null}
      <label className="block text-[11px] font-medium text-crt-fg-dim">用户 ID<input value={params.user_id} onChange={(e) => setParams({ user_id: e.target.value })} disabled={DEV_AUTH_ENABLED} className="field-control mt-1.5 font-mono text-[11px] disabled:cursor-not-allowed disabled:opacity-60" /></label>
      <label className="block text-[11px] font-medium text-crt-fg-dim">租户 ID<input value={params.tenant_id} onChange={(e) => setParams({ tenant_id: e.target.value })} disabled={DEV_AUTH_ENABLED} className="field-control mt-1.5 font-mono text-[11px] disabled:cursor-not-allowed disabled:opacity-60" /></label>
      <label className="block text-[11px] font-medium text-crt-fg-dim">部门<select value={params.department} onChange={(e) => setParams({ department: e.target.value as Department })} disabled={DEV_AUTH_ENABLED} className="field-control mt-1.5 text-[12px] disabled:cursor-not-allowed disabled:opacity-60">{DEPARTMENTS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
      <div><div className="text-[11px] font-medium text-crt-fg-dim">高级推理</div><button onClick={() => setParams({ advanced_reasoning: !params.advanced_reasoning })} className="mt-2 flex w-full items-center justify-between rounded-lg border border-crt-border p-3 text-left"><span><span className="block text-[12px] font-medium">深度思考模式</span><span className="mt-0.5 block text-[10px] text-crt-fg-muted">可能增加响应时间与成本</span></span><span className={`flex h-5 w-9 items-center rounded-full p-0.5 ${params.advanced_reasoning ? 'bg-blue-600' : 'bg-slate-300'}`}><span className={`h-4 w-4 rounded-full bg-white transition-transform ${params.advanced_reasoning ? 'translate-x-4' : ''}`} /></span></button></div>
      <div><div className="text-[11px] font-medium text-crt-fg-dim">会话 ID</div><div className="mt-1.5 break-all rounded-lg bg-crt-bg p-3 font-mono text-[10px] text-crt-fg-muted">{sessionId}</div></div>
    </div>
  </aside>;
}
