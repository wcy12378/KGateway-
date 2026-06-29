/**
 * 聊天消息气泡组件。
 *
 * 本文件负责展示用户、助手和系统消息，包括 Markdown、代码块和元数据栏。
 * 它不负责消息获取、SSE 解析或网关请求发送。
 */
import { useState } from 'react';
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
import { Copy, Check } from 'lucide-react';
import { MetadataBar } from './MetadataBar';
import type { ChatMessage } from '@/types';

interface MessageBubbleProps {
  message: ChatMessage;
}

SyntaxHighlighter.registerLanguage('bash', bash);
SyntaxHighlighter.registerLanguage('javascript', javascript);
SyntaxHighlighter.registerLanguage('js', javascript);
SyntaxHighlighter.registerLanguage('json', json);
SyntaxHighlighter.registerLanguage('python', python);
SyntaxHighlighter.registerLanguage('typescript', typescript);
SyntaxHighlighter.registerLanguage('ts', typescript);
SyntaxHighlighter.registerLanguage('tsx', tsx);

export function MessageBubble({ message }: MessageBubbleProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  // --- User bubble ---
  if (message.role === 'user') {
    return (
      <div className="flex justify-end mb-4">
        <div className="max-w-[88%] sm:max-w-[75%] bg-crt-bg-panel border border-crt-border-strong p-3 rounded-lg shadow-[0_10px_32px_rgba(47,123,255,0.08)]">
          <div className="font-label text-crt-fg-muted mb-1">
            用户
          </div>
          <div className="text-crt-fg text-[12px] font-mono whitespace-pre-wrap">
            {message.content}
          </div>
        </div>
      </div>
    );
  }

  // --- System bubble (error / circuit breaker) ---
  if (message.role === 'system') {
    const isBreaker = message.metadata?.circuit_breaker;
    return (
      <div className="flex justify-center mb-4">
        <div
          className={`max-w-[92%] border p-3 rounded-lg ${
            isBreaker
              ? 'border-crt-red bg-crt-red/10'
              : 'border-crt-border bg-crt-bg-elevated'
          }`}
        >
          <div className="flex items-center gap-2 mb-1">
            <span
              className={`font-label text-[8px] tracking-[0.15em] ${
                isBreaker ? 'text-crt-red' : 'text-crt-fg-muted'
              }`}
            >
              {isBreaker ? '熔断器已触发' : '系统提示'}
            </span>
          </div>
          <div className="text-[12px] font-mono text-crt-fg-dim">
            {message.content}
          </div>
        </div>
      </div>
    );
  }

  // --- Assistant bubble ---
  return (
    <div className="flex justify-start mb-4">
      <div className="max-w-[94%] sm:max-w-[85%] w-full bg-crt-bg-elevated border border-crt-border p-3 rounded-lg">
        <div className="flex items-center justify-between mb-1">
          <span className="font-label text-[8px] text-crt-fg-muted">
            助手
            {message.isStreaming && (
              <span className="ml-2 text-crt-green animate-pulse">
                生成中
              </span>
            )}
          </span>
          <button
            onClick={handleCopy}
            className="icon-button"
            title="复制回复"
            aria-label="复制回复"
          >
            {copied ? <Check size={12} /> : <Copy size={12} />}
          </button>
        </div>

        {/* Markdown content — guard against null/undefined content */}
        <div className="text-crt-fg text-[12px] font-mono leading-relaxed break-words">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              code({ className, children, ...props }) {
                const match = /language-(\w+)/.exec(className || '');
                const codeStr = String(children ?? '').replace(/\n$/, '');

                if (match) {
                  return (
                    <SyntaxHighlighter
                      style={vscDarkPlus as Record<string, React.CSSProperties>}
                      language={match[1]}
                      PreTag="div"
                      customStyle={{
                        background: '#07111F',
                        border: '1px solid rgba(111,151,202,0.24)',
                        padding: '12px',
                        fontSize: '11px',
                        margin: '8px 0',
                        borderRadius: 6,
                      }}
                    >
                      {codeStr}
                    </SyntaxHighlighter>
                  );
                }
                return (
                  <code
                    className="bg-crt-bg text-crt-fg px-1 py-0.5 text-[11px]"
                    {...props}
                  >
                    {children}
                  </code>
                );
              },
              table({ children }) {
                return (
                  <table className="w-full text-[11px] border-collapse my-2">
                    {children}
                  </table>
                );
              },
              th({ children }) {
                return (
                  <th className="text-left p-1.5 border border-crt-border bg-crt-bg text-[9px] font-label text-crt-fg-muted">
                    {children}
                  </th>
                );
              },
              td({ children }) {
                return (
                  <td className="p-1.5 border border-crt-border text-[11px]">
                    {children}
                  </td>
                );
              },
              a({ href, children }) {
                return (
                  <a
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-crt-fg underline underline-offset-2 hover:text-crt-red transition-colors"
                  >
                    {children}
                  </a>
                );
              },
              strong({ children }) {
                return (
                  <strong className="text-crt-fg font-bold">{children}</strong>
                );
              },
            }}
          >
            {message.content ?? ''}
          </ReactMarkdown>

          {/* Streaming cursor */}
          {message.isStreaming && (
            <span className="inline-block w-2 h-4 bg-crt-fg ml-0.5 animate-pulse" />
          )}
        </div>

        {/* Metadata bar */}
        {message.metadata && <MetadataBar metadata={message.metadata} />}
      </div>
    </div>
  );
}
