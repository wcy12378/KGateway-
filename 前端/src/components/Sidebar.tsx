import { useState } from 'react';
import { NavLink } from 'react-router-dom';
import {
  BarChart3, Bell, BookOpen, Braces, Building2, ChevronDown, FileText,
  History, MessageCircle, PanelLeftOpen, ScrollText,
  ShieldCheck, SquarePen, Trash2, Workflow, X,
} from 'lucide-react';
import { useUIStore } from '@/stores/ui';
import { useChatStore } from '@/stores/chat';
import { parseStoredSessions, type SessionEntry } from '@/lib/sessions';

const STORAGE_KEY = 'kagent_sessions';

function loadSessions(): SessionEntry[] {
  return parseStoredSessions(localStorage.getItem(STORAGE_KEY));
}

const GROUPS = [
  { label: '工作台', items: [
    { to: '/', icon: MessageCircle, label: '智能对话' },
    { to: '/workflows', icon: Workflow, label: 'Agent 工作流' },
  ]},
  { label: '管理与观测', items: [
    { to: '/dashboard', icon: BarChart3, label: '运行指标' },
    { to: '/traces', icon: History, label: '链路追踪' },
    { to: '/breaker', icon: ShieldCheck, label: '熔断器' },
    { to: '/prompts', icon: FileText, label: 'Prompt 模板' },
    { to: '/audit', icon: ScrollText, label: '工具审计' },
    { to: '/guide', icon: BookOpen, label: '使用说明' },
  ]},
] as const;

const DEPARTMENT_LABELS: Record<string, string> = {
  general: '通用部门', legal: '法务部', hr: '人力资源部', engineering: '工程部', finance: '财务部',
};

export function Sidebar() {
  const collapsed = useUIStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);
  const mobileMenuOpen = useUIStore((s) => s.mobileMenuOpen);
  const closeMobileMenu = useUIStore((s) => s.closeMobileMenu);
  const currentSessionId = useChatStore((s) => s.currentSessionId);
  const setSessionId = useChatStore((s) => s.setSessionId);
  const clearMessages = useChatStore((s) => s.clearMessages);
  const cancelStreaming = useChatStore((s) => s.cancelStreaming);
  const params = useChatStore((s) => s.gatewayParams);
  const [sessions, setSessions] = useState<SessionEntry[]>(loadSessions);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [organizationOpen, setOrganizationOpen] = useState(false);

  const newSession = () => {
    cancelStreaming();
    const id = crypto.randomUUID();
    const entry = { id, label: `会话 ${new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`, timestamp: Date.now() };
    const next = [entry, ...sessions].slice(0, 8);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    setSessions(next);
    setSessionId(id);
    clearMessages();
    closeMobileMenu();
  };

  const deleteSession = (id: string) => {
    const next = sessions.filter((item) => item.id !== id);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    setSessions(next);
  };

  return <>
    {mobileMenuOpen ? <button className="fixed inset-0 z-40 bg-slate-950/25 md:hidden" onClick={closeMobileMenu} aria-label="关闭导航遮罩" /> : null}
    <aside className={`fixed inset-y-0 left-0 z-50 flex w-[280px] shrink-0 flex-col border-r border-crt-border bg-[#fbfcfe] transition-[width,transform] duration-200 md:static md:z-auto ${collapsed ? 'md:w-[72px]' : 'md:w-[280px]'} ${mobileMenuOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}`}>
      <div className="relative flex h-[76px] shrink-0 items-center gap-3 px-5">
        <span className="brand-mark" role="img" aria-label="KAgent" />
        {!collapsed ? <span className="text-[22px] font-semibold tracking-[-.025em]">KAgent</span> : null}
        <div className="ml-auto flex items-center gap-1">
          {!collapsed ? <>
            <button onClick={newSession} className="sidebar-icon-button inline-flex" aria-label="新建对话" title="新建对话"><SquarePen size={18} /></button>
            <button onClick={() => setNotificationsOpen((value) => !value)} className="sidebar-icon-button inline-flex" aria-label="查看通知" aria-expanded={notificationsOpen}><Bell size={19} /></button>
          </> : null}
          <button onClick={closeMobileMenu} className="sidebar-icon-button inline-flex md:hidden" aria-label="关闭导航"><X size={19} /></button>
        </div>
        {notificationsOpen && !collapsed ? <div className="absolute left-4 right-4 top-[66px] z-50 rounded-xl border border-crt-border bg-white p-3 shadow-lg"><div className="text-[12px] font-semibold">通知</div><p className="mt-1 text-[11px] leading-5 text-crt-fg-muted">暂无新通知，服务运行正常。</p></div> : null}
      </div>

      <div className="px-4 pb-3">
        {!collapsed ? <div className="relative">
          <button onClick={() => setOrganizationOpen((value) => !value)} className="flex h-12 w-full items-center gap-3 rounded-xl border border-crt-border bg-white px-3 text-left hover:border-crt-border-strong" aria-expanded={organizationOpen}>
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-crt-bg text-crt-fg-dim"><Building2 size={17} /></span>
            <span className="min-w-0 flex-1 truncate text-[13px] font-semibold">默认租户</span>
            <ChevronDown size={15} className={`text-crt-fg-muted transition-transform ${organizationOpen ? 'rotate-180' : ''}`} />
          </button>
          {organizationOpen ? <div className="absolute left-0 right-0 top-[52px] z-40 rounded-xl border border-crt-border bg-white p-2 shadow-lg"><button onClick={() => setOrganizationOpen(false)} className="flex w-full items-center gap-2 rounded-lg bg-crt-bg-panel px-3 py-2 text-left text-[12px] font-medium text-blue-700"><Building2 size={14} />默认租户</button></div> : null}
        </div> : <button onClick={newSession} className="mx-auto grid h-10 w-10 place-items-center rounded-xl bg-blue-600 text-white" aria-label="新建对话"><SquarePen size={17} /></button>}
      </div>

      <div className="flex-1 overflow-y-auto px-3 pb-4">
        {GROUPS.map((group, groupIndex) => <div key={group.label} className={groupIndex ? 'mt-4 border-t border-crt-border pt-4' : ''}>
          {!collapsed ? <div className="mb-2 px-3 text-[12px] font-medium text-crt-fg-muted">{group.label}</div> : null}
          <nav className="space-y-1">{group.items.map((item) => <NavLink key={item.to} to={item.to} end={item.to === '/'} onClick={closeMobileMenu} title={collapsed ? item.label : undefined} className={({ isActive }) => `relative flex h-11 items-center gap-3 rounded-[10px] px-3 text-[14px] font-medium ${isActive ? 'bg-crt-bg-panel text-blue-700 before:absolute before:-left-3 before:h-7 before:w-[3px] before:rounded-r-full before:bg-blue-600' : 'text-crt-fg-dim hover:bg-crt-bg hover:text-crt-fg'} ${collapsed ? 'justify-center' : ''}`}><item.icon size={19} strokeWidth={1.9} />{!collapsed ? <span>{item.label}</span> : null}</NavLink>)}</nav>
        </div>)}

          {!collapsed && sessions.length ? <div className="mt-4 border-t border-crt-border pt-4"><div className="mb-2 px-3 text-[12px] font-medium text-crt-fg-muted">最近会话</div>{sessions.slice(0, 4).map((session) => <div key={session.id} className={`group flex h-9 items-center gap-2 rounded-lg px-3 text-[12px] ${session.id === currentSessionId ? 'bg-white text-crt-fg' : 'text-crt-fg-muted hover:bg-white'}`}><Braces size={13} /><button className="min-w-0 flex-1 truncate text-left" onClick={() => { cancelStreaming(); setSessionId(session.id); clearMessages(); }}>{session.label}</button><button onClick={() => deleteSession(session.id)} className="opacity-0 group-hover:opacity-100" aria-label="删除会话"><Trash2 size={12} /></button></div>)}</div> : null}
      </div>

      <div className="border-t border-crt-border p-4">
        <div className={`flex items-center ${collapsed ? 'justify-center' : 'gap-3'}`}>
          <span className="relative grid h-10 w-10 shrink-0 place-items-center rounded-full bg-blue-100 text-[12px] font-semibold text-blue-800">{params.user_id.slice(0, 2).toUpperCase()}<span className="absolute bottom-0 right-0 h-3 w-3 rounded-full border-2 border-white bg-emerald-500" /></span>
          {!collapsed ? <><div className="min-w-0 flex-1"><div className="truncate text-[13px] font-semibold">{params.user_id}</div><div className="mt-0.5 text-[11px] text-crt-fg-muted">{DEPARTMENT_LABELS[params.department] ?? params.department}</div></div><button onClick={toggleSidebar} className="sidebar-icon-button inline-flex" aria-label="收起侧边栏"><ChevronDown size={16} className="-rotate-90" /></button></> : <button onClick={toggleSidebar} className="sidebar-icon-button inline-flex" aria-label="展开侧边栏"><PanelLeftOpen size={17} /></button>}
        </div>
      </div>
    </aside>
  </>;
}
