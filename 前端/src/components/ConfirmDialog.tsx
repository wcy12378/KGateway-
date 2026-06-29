/**
 * 通用确认弹窗组件。
 *
 * 本文件负责展示危险操作确认对话框，并把确认或取消事件回传给调用方。
 * 它不负责具体业务操作、接口请求或权限判断。
 */
import { useEffect, useRef } from 'react';
import { AlertTriangle } from 'lucide-react';

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const backdropRef = useRef<HTMLDivElement>(null);

  // 按 ESC 关闭弹窗。
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div
      ref={backdropRef}
      className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/75 backdrop-blur-sm p-4"
      onClick={(e) => {
        if (e.target === backdropRef.current) onCancel();
      }}
    >
      <div className="w-full max-w-[420px] bg-crt-bg-panel border border-crt-red rounded-lg overflow-hidden shadow-2xl">
        {/* Header */}
        <div className="flex items-center gap-2 px-4 py-3 border-b border-crt-border bg-crt-red/10">
          <AlertTriangle size={16} className="text-crt-red" />
          <span className="font-label text-crt-red tracking-[0.15em]">
            {title}
          </span>
        </div>

        {/* Body */}
        <div className="px-4 py-4">
          <p className="text-crt-fg text-[12px] font-mono leading-relaxed">
            {message}
          </p>
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-2 px-4 py-3 border-t border-crt-border">
          <button
            onClick={onCancel}
            className="px-4 py-1.5 border border-crt-border text-crt-fg-dim font-label tracking-widest hover:border-crt-border-strong hover:text-crt-fg transition-colors rounded-md"
          >
            取消
          </button>
          <button
            onClick={onConfirm}
            className="px-4 py-1.5 bg-crt-red text-crt-bg font-label tracking-widest hover:bg-crt-red/80 transition-colors rounded-md"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
