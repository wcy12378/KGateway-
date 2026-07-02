import { ArrowUpRight, BookOpen, FileSearch, Scale } from 'lucide-react';
import { Virtuoso } from 'react-virtuoso';
import { useChatStore } from '@/stores/chat';
import { MessageBubble } from './MessageBubble';

const PROMPTS = [
  { icon: FileSearch, text: '总结最新的产品需求文档' },
  { icon: Scale, text: '检索合同审查的内部规范' },
  { icon: BookOpen, text: '帮我梳理本周项目风险' },
] as const;

export function MessageList() {
  const messages = useChatStore((s) => s.messages);
  if (!messages.length) return (
    <div className="flex h-full min-h-[360px] items-center justify-center px-5 py-10">
      <div className="w-full max-w-xl">
        <div className="mb-7 text-center">
          <span className="brand-mark brand-mark-lg mx-auto mb-4" role="img" aria-label="KAgent" />
          <h2 className="text-[22px] font-semibold tracking-[-.02em]">今天需要处理什么？</h2>
          <p className="mt-2 text-[13px] text-crt-fg-dim">连接企业知识库与工具，给出可追踪的工作结果。</p>
        </div>
        <div className="grid gap-2 sm:grid-cols-3">{PROMPTS.map(({ icon: Icon, text }) => <button key={text} onClick={() => window.dispatchEvent(new CustomEvent('chat:send', { detail: { text } }))} className="group flex min-h-[96px] flex-col items-start justify-between rounded-[10px] border border-crt-border bg-white p-3 text-left hover:border-slate-300 hover:bg-crt-bg">
          <Icon size={16} className="text-crt-fg-muted" /><span className="mt-3 text-[12px] leading-5 text-crt-fg-dim">{text}</span><ArrowUpRight size={14} className="self-end text-crt-fg-muted opacity-0 group-hover:opacity-100" />
        </button>)}</div>
      </div>
    </div>
  );

  return <Virtuoso data={messages} computeItemKey={(_, message) => message.id} itemContent={(_, message) => <MessageBubble message={message} />} overscan={240} followOutput="smooth" style={{ height: '100%' }} />;
}
