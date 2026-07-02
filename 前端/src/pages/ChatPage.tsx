import { useState } from 'react';
import { Settings2, UserPlus, UserRound, X } from 'lucide-react';
import { ParamPanel } from '@/components/chat/ParamPanel';
import { MessageList } from '@/components/chat/MessageList';
import { ChatInput } from '@/components/chat/ChatInput';
import { useSSEStream } from '@/hooks/useSSE';

export default function ChatPage() {
  const [panelOpen, setPanelOpen] = useState(false);
  const [collaboratorsOpen, setCollaboratorsOpen] = useState(false);
  useSSEStream();

  return <div className="relative flex h-[calc(100dvh-3.5rem)] md:h-[100dvh]">
    <section className="flex min-w-0 flex-1 flex-col overflow-hidden bg-white">
      <header className="relative flex h-[76px] shrink-0 items-center border-b border-crt-border px-5 sm:px-8">
        <h1 className="text-[22px] font-semibold tracking-[-.025em] sm:text-[24px]">智能对话</h1>
        <div className="ml-auto flex items-center gap-3">
          <div className="hidden items-center gap-2 text-[13px] text-crt-fg-dim sm:flex"><span className="h-2 w-2 rounded-full bg-emerald-500" />企业知识助手 · 在线</div>
          <div className="hidden items-center -space-x-2 lg:flex" aria-label="在线协作者">
            <span className="grid h-8 w-8 place-items-center rounded-full border-2 border-white bg-sky-100 text-sky-800"><UserRound size={15} /></span>
            <span className="grid h-8 w-8 place-items-center rounded-full border-2 border-white bg-indigo-100 text-indigo-800"><UserRound size={15} /></span>
          </div>
          <button onClick={() => setCollaboratorsOpen((value) => !value)} className="icon-button hidden sm:inline-flex" aria-label="查看协作者" aria-expanded={collaboratorsOpen}><UserPlus size={17} /></button>
          <button onClick={() => setPanelOpen((value) => !value)} className="button-secondary" aria-expanded={panelOpen}>{panelOpen ? <X size={15} /> : <Settings2 size={15} />}<span className="hidden sm:inline">请求设置</span></button>
        </div>
        {collaboratorsOpen ? <div className="absolute right-8 top-[64px] z-40 w-56 rounded-xl border border-crt-border bg-white p-3 shadow-lg"><div className="text-[12px] font-semibold">当前协作者</div><div className="mt-2 flex items-center gap-2 rounded-lg bg-crt-bg p-2"><span className="grid h-7 w-7 place-items-center rounded-full bg-blue-100 text-blue-800"><UserRound size={14} /></span><span className="text-[11px] text-crt-fg-dim">默认用户 · 在线</span></div></div> : null}
      </header>
      <div className="min-h-0 flex-1"><MessageList /></div>
      <ChatInput />
    </section>

    {panelOpen ? <><button className="fixed inset-0 z-30 bg-slate-950/20 lg:hidden" onClick={() => setPanelOpen(false)} aria-label="关闭设置遮罩" /><ParamPanel onClose={() => setPanelOpen(false)} /></> : null}
  </div>;
}
