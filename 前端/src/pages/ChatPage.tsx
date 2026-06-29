/**
 * 聊天主页面。
 *
 * 本文件负责组合参数面板、消息列表和输入框，并处理移动端参数面板展开。
 * 它不负责 SSE 连接、请求构造或后端协议解析。
 */
import { useState } from 'react';
import { PanelLeftClose, PanelLeftOpen, SlidersHorizontal, X } from 'lucide-react';
import { ParamPanel } from '@/components/chat/ParamPanel';
import { MessageList } from '@/components/chat/MessageList';
import { ChatInput } from '@/components/chat/ChatInput';
import { useSSEStream } from '@/hooks/useSSE';

export default function ChatPage() {
  const [panelOpen, setPanelOpen] = useState(true);

  // Mount SSE listener
  useSSEStream();

  return (
    <div className="relative flex h-[calc(100dvh-72px)] gap-3">
      {panelOpen && (
        <>
          <button
            className="fixed inset-0 z-30 bg-slate-950/70 backdrop-blur-sm md:hidden"
            onClick={() => setPanelOpen(false)}
            aria-label="关闭参数面板遮罩"
          />
          <ParamPanel onClose={() => setPanelOpen(false)} />
        </>
      )}

      {/* Right: chat area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header bar */}
        <div className="flex items-center gap-3 min-h-11 border border-crt-border bg-crt-bg-elevated px-3 shrink-0 rounded-lg">
          <button
            onClick={() => setPanelOpen(!panelOpen)}
            className="icon-button"
            aria-label={panelOpen ? '隐藏参数' : '显示参数'}
            title={panelOpen ? '隐藏参数' : '显示参数'}
          >
            <span className="hidden md:inline-flex">
            {panelOpen ? (
              <PanelLeftClose size={14} />
            ) : (
              <PanelLeftOpen size={14} />
            )}
            </span>
            <span className="inline-flex md:hidden">
              {panelOpen ? <X size={14} /> : <SlidersHorizontal size={14} />}
            </span>
          </button>
          <span className="font-macro text-[18px] text-crt-fg tracking-tight">
            智能对话
          </span>
          <span className="hidden sm:inline font-label text-crt-fg-muted">
            流式响应交互界面
          </span>
        </div>

        {/* Message list (virtuoso) */}
        <div className="flex-1 min-h-0">
          <MessageList />
        </div>

        {/* Input bar */}
        <div className="shrink-0">
          <ChatInput />
        </div>
      </div>
    </div>
  );
}
