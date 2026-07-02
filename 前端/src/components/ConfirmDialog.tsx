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
      className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/30 p-4"
      onClick={(e) => {
        if (e.target === backdropRef.current) onCancel();
      }}
    >
      <div className="w-full max-w-[420px] overflow-hidden rounded-[10px] border border-crt-border bg-white shadow-xl">
        {/* Header */}
        <div className="flex items-center gap-2 border-b border-crt-border px-4 py-3">
          <AlertTriangle size={16} className="text-crt-red" />
          <span className="text-[13px] font-semibold text-crt-fg">
            {title}
          </span>
        </div>

        {/* Body */}
        <div className="px-4 py-4">
          <p className="text-[12px] leading-6 text-crt-fg-dim">
            {message}
          </p>
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-2 px-4 py-3 border-t border-crt-border">
          <button
            onClick={onCancel}
            className="button-secondary"
          >
            取消
          </button>
          <button
            onClick={onConfirm}
            className="button-danger"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
