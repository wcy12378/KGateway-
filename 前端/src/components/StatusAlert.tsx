/**
 * 页面级状态提示。
 *
 * 本组件统一展示请求错误或提示信息，并可提供重试操作。
 */
import { AlertCircle, RefreshCw, X } from 'lucide-react';

interface StatusAlertProps {
  message: string;
  onRetry?: () => void;
  onDismiss?: () => void;
}

export function StatusAlert({ message, onRetry, onDismiss }: StatusAlertProps) {
  return (
    <div className="status-alert" role="alert">
      <AlertCircle size={16} aria-hidden="true" />
      <span className="flex-1">{message}</span>
      {onRetry && (
        <button className="icon-button" onClick={onRetry} aria-label="重新请求" title="重新请求">
          <RefreshCw size={15} />
        </button>
      )}
      {onDismiss && (
        <button className="icon-button" onClick={onDismiss} aria-label="关闭提示" title="关闭提示">
          <X size={15} />
        </button>
      )}
    </div>
  );
}
