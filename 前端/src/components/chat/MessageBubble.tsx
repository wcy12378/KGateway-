import { memo, useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { PrismLight as SyntaxHighlighter } from 'react-syntax-highlighter';
import bash from 'react-syntax-highlighter/dist/esm/languages/prism/bash';
import javascript from 'react-syntax-highlighter/dist/esm/languages/prism/javascript';
import json from 'react-syntax-highlighter/dist/esm/languages/prism/json';
import python from 'react-syntax-highlighter/dist/esm/languages/prism/python';
import typescript from 'react-syntax-highlighter/dist/esm/languages/prism/typescript';
import tsx from 'react-syntax-highlighter/dist/esm/languages/prism/tsx';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Bot, Check, Copy, LoaderCircle } from 'lucide-react';
import { MetadataBar } from './MetadataBar';
import { useChatStore } from '@/stores/chat';
import type { ChatMessage } from '@/types';

SyntaxHighlighter.registerLanguage('bash', bash);
SyntaxHighlighter.registerLanguage('javascript', javascript);
SyntaxHighlighter.registerLanguage('js', javascript);
SyntaxHighlighter.registerLanguage('json', json);
SyntaxHighlighter.registerLanguage('python', python);
SyntaxHighlighter.registerLanguage('typescript', typescript);
SyntaxHighlighter.registerLanguage('ts', typescript);
SyntaxHighlighter.registerLanguage('tsx', tsx);

const PHASE_LABELS = {
  checking_cache: '正在检查缓存',
  cache_hit: '正在读取缓存答案',
  running_fast_lane: '正在执行安全极速通道',
  retrieving_knowledge: '正在检索企业知识库',
  waiting_provider: '正在等待模型首字',
  running_agent: 'Agent 正在处理任务',
} as const;

export const MessageBubble = memo(function MessageBubble({ message }: { message: ChatMessage }) {
  const [copied, setCopied] = useState(false);
  const copyTimerRef = useRef<number | null>(null);
  const userId = useChatStore((s) => s.gatewayParams.user_id);
  const displayContent = message.role === 'assistant'
    ? message.content.replace(/^Processing via [^.\n]+\.\.\.Generating via [^.\n]+\.\.\./, '').trimStart()
    : message.content;

  useEffect(() => () => {
    if (copyTimerRef.current !== null) window.clearTimeout(copyTimerRef.current);
  }, []);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(displayContent);
      setCopied(true);
      if (copyTimerRef.current !== null) window.clearTimeout(copyTimerRef.current);
      copyTimerRef.current = window.setTimeout(() => setCopied(false), 1500);
    } catch (error) {
      console.warn('回复复制失败', error);
    }
  };

  if (message.role === 'user') return <div className="mx-auto flex w-full max-w-[1080px] justify-end gap-3 px-4 py-5 sm:px-6">
    <div className="max-w-[82%] rounded-[16px] rounded-br-[4px] border border-blue-200 bg-blue-50 px-5 py-4 text-[14px] leading-6 text-crt-fg sm:max-w-[72%]">{message.content}</div>
    <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-blue-100 text-[11px] font-semibold text-blue-800">{userId.slice(0, 2).toUpperCase()}</span>
  </div>;

  if (message.role === 'system') {
    const breaker = message.metadata?.circuit_breaker;
    return <div className="mx-auto w-full max-w-[1080px] px-4 py-3 sm:px-6"><div className={`rounded-xl border px-4 py-3 text-[12px] leading-5 ${breaker ? 'border-red-200 bg-red-50 text-red-800' : 'border-crt-border bg-crt-bg text-crt-fg-dim'}`}><div className="mb-1 font-semibold">{breaker ? '熔断器已触发' : '系统提示'}</div>{message.content}</div></div>;
  }

  return <div className="mx-auto w-full max-w-[1080px] px-4 py-5 sm:px-6">
    <div className="flex items-start gap-3 sm:gap-4">
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-blue-600 text-white shadow-sm"><Bot size={23} /></span>
      <div className="min-w-0 flex-1">
        <article className="rounded-[16px] rounded-tl-[5px] border border-crt-border bg-white p-4 sm:p-6">
          <div className="mb-2 flex items-center justify-between gap-3"><span className="text-[12px] font-semibold text-crt-fg-dim">KAgent</span><button onClick={copy} className="icon-button" title="复制回复" aria-label="复制回复">{copied ? <Check size={14} /> : <Copy size={14} />}</button></div>
          <div className="break-words text-[14px] leading-7 text-crt-fg">
            {message.phase ? <div className="flex items-center gap-2 py-2 text-[12px] text-crt-fg-muted"><LoaderCircle size={14} className="animate-spin" />{PHASE_LABELS[message.phase]}</div> : null}
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
              h1: ({ children }) => <h2 className="mb-3 text-[19px] font-semibold tracking-[-.015em]">{children}</h2>,
              h2: ({ children }) => <h3 className="mb-2 mt-4 text-[17px] font-semibold">{children}</h3>,
              h3: ({ children }) => <h4 className="mb-2 mt-3 text-[15px] font-semibold">{children}</h4>,
              p: ({ children }) => <p className="my-2 max-w-[72ch]">{children}</p>,
              ul: ({ children }) => <ul className="my-3 max-w-[72ch] list-disc space-y-1.5 pl-6">{children}</ul>,
              ol: ({ children }) => <ol className="my-3 max-w-[72ch] list-decimal space-y-1.5 pl-6">{children}</ol>,
              li: ({ children }) => <li className="pl-1">{children}</li>,
              code({ className, children, ...props }) {
                const match = /language-(\w+)/.exec(className || '');
                const code = String(children ?? '').replace(/\n$/, '');
                if (match) return <SyntaxHighlighter style={vscDarkPlus as Record<string, React.CSSProperties>} language={match[1]} PreTag="div" customStyle={{ background: '#111827', border: '1px solid #253047', padding: 14, fontSize: 12, margin: '12px 0', borderRadius: 10 }}>{code}</SyntaxHighlighter>;
                return <code className="rounded bg-crt-bg px-1.5 py-0.5 font-mono text-[12px]" {...props}>{children}</code>;
              },
              table: ({ children }) => <div className="my-3 overflow-x-auto"><table className="min-w-[520px] text-[12px]">{children}</table></div>,
              th: ({ children }) => <th className="border-b border-crt-border bg-crt-bg px-3 py-2 text-left font-semibold">{children}</th>,
              td: ({ children }) => <td className="border-b border-crt-border px-3 py-2">{children}</td>,
              a: ({ href, children }) => <a href={href} target="_blank" rel="noopener noreferrer" className="text-blue-700 underline underline-offset-2 hover:text-blue-800">{children}</a>,
              strong: ({ children }) => <strong className="font-semibold text-crt-fg">{children}</strong>,
            }}>{displayContent}</ReactMarkdown>
            {message.isStreaming ? <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse rounded-sm bg-blue-600" /> : null}
          </div>
        </article>
        {message.metadata ? <MetadataBar metadata={message.metadata} /> : null}
      </div>
    </div>
  </div>;
});
