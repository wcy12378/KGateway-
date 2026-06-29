/**
 * 聊天输入组件。
 *
 * 本文件负责采集用户输入、提交发送事件和处理停止生成操作。它不负责
 * 组装网关请求、解析 SSE 响应或保存完整聊天状态。
 */
import { useState, useRef, useCallback } from 'react';
import { Send, Square } from 'lucide-react';
import { useChatStore } from '@/stores/chat';

export function ChatInput() {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const abortController = useChatStore((s) => s.abortController);

  const handleCancel = useCallback(() => {
    abortController?.abort();
  }, [abortController]);

  const handleSubmit = useCallback(() => {
    // This will be connected via onSend prop in ChatPage
    // For now, dispatch a custom event that ChatPage listens to
    const trimmed = value.trim();
    if (!trimmed) return;
    window.dispatchEvent(
      new CustomEvent('chat:send', { detail: { text: trimmed } })
    );
    setValue('');
  }, [value]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!isStreaming) handleSubmit();
    }
  };

  return (
    <div className="flex flex-col gap-2 mt-3 sm:flex-row">
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={isStreaming}
        className="flex-1 bg-crt-bg-elevated border border-crt-border text-crt-fg text-[13px] font-mono p-3 resize-none min-h-16 placeholder:text-crt-fg-muted focus:outline-none focus:border-crt-border-strong disabled:opacity-40"
        placeholder={isStreaming ? '正在流式生成...' : '输入请求内容，Enter 发送，Shift+Enter 换行'}
      />
      {isStreaming ? (
        <button
          onClick={handleCancel}
          className="px-4 py-3 bg-crt-red text-crt-bg font-label tracking-widest hover:bg-crt-red/80 transition-colors flex items-center justify-center gap-2 rounded-md"
        >
          <Square size={12} />
          停止
        </button>
      ) : (
        <button
          onClick={handleSubmit}
          disabled={!value.trim()}
          className="px-5 py-3 bg-crt-border-strong text-crt-fg font-label tracking-widest hover:bg-[#57A0FF] hover:text-crt-bg transition-colors disabled:opacity-30 disabled:hover:bg-crt-border-strong flex items-center justify-center gap-2 rounded-md"
        >
          <Send size={12} />
          发送
        </button>
      )}
    </div>
  );
}
