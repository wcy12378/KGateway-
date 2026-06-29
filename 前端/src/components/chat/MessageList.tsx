/**
 * 聊天消息列表组件。
 *
 * 本文件负责虚拟化渲染聊天消息并在消息变化时滚动到底部。它不负责消息
 * 内容生成、参数配置或后端连接。
 */
import { useRef, useEffect } from 'react';
import { Virtuoso } from 'react-virtuoso';
import type { VirtuosoHandle } from 'react-virtuoso';
import { useChatStore } from '@/stores/chat';
import { MessageBubble } from './MessageBubble';

export function MessageList() {
  const messages = useChatStore((s) => s.messages);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const virtuosoRef = useRef<VirtuosoHandle>(null);

  // Auto-scroll to bottom during streaming
  useEffect(() => {
    if (messages.length > 0) {
      virtuosoRef.current?.scrollToIndex({
        index: messages.length - 1,
        behavior: 'smooth',
        align: 'end',
      });
    }
  }, [messages, isStreaming]);

  if (messages.length === 0) {
    return (
      <div className="flex-1 border border-crt-border bg-crt-bg-elevated flex flex-col items-center justify-center gap-3 rounded-lg px-6 text-center">
        <div className="font-label text-crt-fg-muted tracking-[0.2em]">
          等待输入
        </div>
        <div className="text-crt-fg-dim text-[13px] font-mono max-w-md leading-relaxed">
          <span className="text-crt-border-strong">&gt;&gt;&gt;</span> KAgent AI
          网关控制台已就绪。
          <br />
          输入请求后将通过 SSE 流式返回模型响应。
        </div>
        <div className="mt-4 font-label text-crt-fg-muted">
          回车发送 · Shift+Enter 换行
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 border border-crt-border bg-crt-bg-elevated overflow-hidden rounded-lg">
      <Virtuoso
        ref={virtuosoRef}
        data={messages}
        itemContent={(index, msg) => <MessageBubble key={msg.id} message={msg} />}
        overscan={200}
        style={{ height: '100%' }}
        followOutput="smooth"
        className="p-4"
      />
    </div>
  );
}
