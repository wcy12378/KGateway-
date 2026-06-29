/**
 * 聊天请求参数面板。
 *
 * 本文件负责维护用户可编辑的网关参数，例如租户、用户、部门和高级推理开关。
 * 它不负责发送请求、展示回答或解析后端响应。
 */
import { useChatStore } from '@/stores/chat';
import type { Department } from '@/types';

const DEPARTMENTS: Department[] = ['legal', 'hr', 'engineering', 'finance', 'general'];
const DEPARTMENT_LABELS: Record<Department, string> = {
  legal: '法务',
  hr: '人力',
  engineering: '工程',
  finance: '财务',
  general: '通用',
};

interface ParamPanelProps {
  onClose?: () => void;
}

export function ParamPanel({ onClose }: ParamPanelProps) {
  const params = useChatStore((s) => s.gatewayParams);
  const setParams = useChatStore((s) => s.setGatewayParams);
  const sessionId = useChatStore((s) => s.currentSessionId);

  return (
    <div className="fixed inset-y-0 left-0 z-40 w-72 shrink-0 border-r border-crt-border bg-crt-bg-elevated flex flex-col overflow-hidden shadow-2xl md:static md:z-auto md:w-60 md:rounded-lg md:border md:shadow-none">
      {/* Header */}
      <div className="h-11 flex items-center px-3 border-b border-crt-border">
        <span className="font-label text-crt-fg-muted tracking-[0.15em]">
          请求参数
        </span>
        {onClose && (
          <button
            className="icon-button ml-auto md:hidden"
            onClick={onClose}
            aria-label="关闭参数面板"
          >
            ×
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-4">
        {/* user_id */}
        <div>
          <label className="block font-label text-[10px] text-crt-fg-muted mb-1">
            用户 ID *
          </label>
          <input
            type="text"
            value={params.user_id}
            onChange={(e) => setParams({ user_id: e.target.value })}
            className="w-full bg-crt-bg border border-crt-border text-crt-fg text-[11px] font-mono px-2 py-1.5 focus:outline-none focus:border-crt-fg-dim placeholder:text-crt-fg-muted"
            placeholder="default_user"
          />
        </div>

        {/* tenant_id */}
        <div>
          <label className="block font-label text-[10px] text-crt-fg-muted mb-1">
            租户 ID *
          </label>
          <input
            type="text"
            value={params.tenant_id}
            onChange={(e) => setParams({ tenant_id: e.target.value })}
            className="w-full bg-crt-bg border border-crt-border text-crt-fg text-[11px] font-mono px-2 py-1.5 focus:outline-none focus:border-crt-fg-dim placeholder:text-crt-fg-muted"
            placeholder="default_tenant"
          />
        </div>

        {/* department */}
        <div>
          <label className="block font-label text-[10px] text-crt-fg-muted mb-1">
            部门 *
          </label>
          <select
            value={params.department}
            onChange={(e) => setParams({ department: e.target.value as Department })}
            className="w-full bg-crt-bg border border-crt-border text-crt-fg text-[11px] font-mono px-2 py-1.5 focus:outline-none focus:border-crt-fg-dim"
          >
            {DEPARTMENTS.map((d) => (
              <option key={d} value={d}>
                {DEPARTMENT_LABELS[d]}
              </option>
            ))}
          </select>
        </div>

        {/* advanced_reasoning */}
        <div>
          <label className="block font-label text-[10px] text-crt-fg-muted mb-1.5">
            高级推理
          </label>
          <button
            onClick={() => setParams({ advanced_reasoning: !params.advanced_reasoning })}
            className="flex items-center gap-2 w-full"
          >
            <div
              className={`w-8 h-[18px] border flex items-center px-0.5 transition-colors ${
                params.advanced_reasoning
                  ? 'bg-crt-border-strong border-crt-border-strong'
                  : 'bg-crt-bg border-crt-border'
              }`}
            >
              <div
                className={`w-3 h-3 bg-crt-fg transition-transform duration-150 ${
                  params.advanced_reasoning ? 'translate-x-3' : 'translate-x-0'
                }`}
              />
            </div>
            <span className="font-mono text-[11px] text-crt-fg-dim">
              {params.advanced_reasoning ? '开启' : '关闭'}
            </span>
          </button>
          <div className="font-label text-[10px] text-crt-fg-muted mt-1">
            开启后将路由到深度推理模型
          </div>
        </div>

        {/* session_id (read-only) */}
        <div>
          <label className="block font-label text-[10px] text-crt-fg-muted mb-1">
            会话 ID
          </label>
          <div className="w-full bg-crt-bg border border-crt-border text-crt-fg-muted text-[10px] font-mono px-2 py-1.5 break-all select-all">
            {sessionId}
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="border-t border-crt-border px-3 py-2">
        <div className="font-label text-[10px] text-crt-fg-muted leading-relaxed">
          网关请求参数<br />
          修改后会随下一次请求生效
        </div>
      </div>
    </div>
  );
}
