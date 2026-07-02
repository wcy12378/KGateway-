import { useCallback, useRef, useState } from 'react';
import { AtSign, Send, Sparkles, Square } from 'lucide-react';
import { useChatStore } from '@/stores/chat';

export function ChatInput() {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const abortController = useChatStore((s) => s.abortController);
  const advancedReasoning = useChatStore((s) => s.gatewayParams.advanced_reasoning);
  const setGatewayParams = useChatStore((s) => s.setGatewayParams);

  const submit = useCallback(() => {
    const text = value.trim();
    if (!text || isStreaming) return;
    window.dispatchEvent(new CustomEvent('chat:send', { detail: { text } }));
    setValue('');
  }, [isStreaming, value]);

  const insertMention = () => {
    const textarea = textareaRef.current;
    const start = textarea?.selectionStart ?? value.length;
    const next = `${value.slice(0, start)}@${value.slice(start)}`;
    setValue(next);
    window.requestAnimationFrame(() => {
      textarea?.focus();
      textarea?.setSelectionRange(start + 1, start + 1);
    });
  };

  return <div className="shrink-0 bg-white px-4 pb-4 sm:px-8 sm:pb-6">
    <div className="mx-auto max-w-[1080px] rounded-[16px] border border-crt-border bg-white p-3 focus-within:border-blue-400 focus-within:shadow-[0_0_0_3px_rgba(37,99,235,.08)] sm:p-4">
      <textarea ref={textareaRef} value={value} onChange={(event) => setValue(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); submit(); } }} disabled={isStreaming} className="min-h-[62px] w-full resize-none border-0 bg-transparent px-1 text-[14px] leading-6 text-crt-fg outline-none placeholder:text-slate-500 disabled:opacity-50 sm:min-h-[70px]" placeholder={isStreaming ? '正在生成回答…' : '输入问题，按 Enter 发送'} />
      <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
        <button type="button" onClick={insertMention} className="composer-tool" aria-label="插入提及" title="插入提及"><AtSign size={20} /></button>
        <button type="button" onClick={() => setGatewayParams({ advanced_reasoning: !advancedReasoning })} className={`composer-tool ${advancedReasoning ? 'bg-blue-50 text-blue-700' : ''}`} aria-pressed={advancedReasoning} aria-label="切换高级推理" title="高级推理"><Sparkles size={20} /></button>
        <span className="hidden text-[11px] text-crt-fg-muted sm:inline">{advancedReasoning ? '已启用高级推理' : '标准智能对话'}</span>
        <label className="ml-auto"><span className="sr-only">对话模式</span><select value={advancedReasoning ? 'advanced' : 'standard'} onChange={(event) => setGatewayParams({ advanced_reasoning: event.target.value === 'advanced' })} className="h-9 rounded-lg border border-crt-border bg-white px-3 text-[12px] text-crt-fg-dim outline-none focus:border-blue-500"><option value="standard">智能对话</option><option value="advanced">高级推理</option></select></label>
        {isStreaming ? <button onClick={() => abortController?.abort()} className="button-secondary h-9 px-4" aria-label="停止生成"><Square size={12} fill="currentColor" />停止</button> : <button onClick={submit} disabled={!value.trim()} className="button-primary h-9 px-5"><Send size={14} />发送</button>}
      </div>
    </div>
    <div className="mx-auto mt-2 flex max-w-[1080px] items-center justify-between px-1 text-[10px] text-crt-fg-muted"><span>回答由 AI 生成，请核验重要信息</span><span>Shift + Enter 换行</span></div>
  </div>;
}
