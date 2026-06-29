/**
 * 应用侧边栏组件。
 *
 * 本文件负责导航入口、会话列表和侧边栏展开收起交互。它不负责页面路由定义、
 * 聊天请求发送或后端数据解析。
 */
import { useState } from 'react';
import { NavLink } from 'react-router-dom';
import {
  MessageSquare,
  BarChart3,
  Shield,
  History,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Trash2,
  X,
  BookOpen,
} from 'lucide-react';
import { useUIStore } from '@/stores/ui';
import { useChatStore } from '@/stores/chat';

// ---- Session history persisted in localStorage ----
interface SessionEntry {
  id: string;
  label: string;
  timestamp: number;
}

const STORAGE_KEY = 'kagent_sessions';

function loadSessions(): SessionEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveSessions(sessions: SessionEntry[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
}

// ---- Nav items ----
const NAV_ITEMS = [
  { to: '/', icon: MessageSquare, label: '智能对话' },
  { to: '/dashboard', icon: BarChart3, label: '运行指标' },
  { to: '/breaker', icon: Shield, label: '熔断器' },
  { to: '/traces', icon: History, label: '链路追踪' },
  { to: '/guide', icon: BookOpen, label: '使用说明' },
] as const;

export function Sidebar() {
  const collapsed = useUIStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);
  const mobileMenuOpen = useUIStore((s) => s.mobileMenuOpen);
  const closeMobileMenu = useUIStore((s) => s.closeMobileMenu);
  const currentSessionId = useChatStore((s) => s.currentSessionId);
  const setSessionId = useChatStore((s) => s.setSessionId);
  const clearMessages = useChatStore((s) => s.clearMessages);

  const [sessions, setSessions] = useState<SessionEntry[]>(loadSessions);

  const handleNewSession = () => {
    const newId = crypto.randomUUID();
    setSessionId(newId);
    clearMessages();
    const entry: SessionEntry = {
      id: newId,
      label: `会话 ${new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`,
      timestamp: Date.now(),
    };
    const next = [entry, ...sessions].slice(0, 50);
    setSessions(next);
    saveSessions(next);
  };

  const handleDeleteSession = (id: string) => {
    const next = sessions.filter((s) => s.id !== id);
    setSessions(next);
    saveSessions(next);
  };

  return (
    <>
    {mobileMenuOpen && (
      <button
        className="fixed inset-0 z-40 bg-slate-950/70 backdrop-blur-sm md:hidden"
        onClick={closeMobileMenu}
        aria-label="关闭导航遮罩"
      />
    )}
    <aside
      className={`fixed inset-y-0 left-0 z-50 flex flex-col w-72 shrink-0 border-r border-crt-border bg-crt-bg/95 backdrop-blur-xl transition-transform duration-200 ease-out overflow-hidden md:static md:z-auto ${collapsed ? 'md:w-14' : 'md:w-56'} ${
        mobileMenuOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'
      }`}
    >
      {/* ---- Header ---- */}
      <div className="flex items-center h-12 border-b border-crt-border px-3 gap-2">
        {!collapsed && (
          <span className="font-macro text-[11px] tracking-widest text-crt-fg truncate">
            KAGENT
          </span>
        )}
        <button
          onClick={toggleSidebar}
          className="ml-auto hidden text-crt-fg-dim hover:text-crt-fg transition-colors md:inline-flex"
          aria-label={collapsed ? '展开侧边栏' : '收起侧边栏'}
        >
          {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
        </button>
        <button
          onClick={closeMobileMenu}
          className="ml-auto text-crt-fg-dim hover:text-crt-fg transition-colors md:hidden"
          aria-label="关闭导航"
        >
          <X size={16} />
        </button>
      </div>

      {/* ---- Navigation ---- */}
      <nav className="flex flex-col gap-0.5 p-2 border-b border-crt-border">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 h-8 px-2 text-[11px] font-label transition-colors ${
                isActive
                  ? 'bg-crt-bg-panel text-crt-fg border-l-2 border-crt-border-strong shadow-[inset_0_0_0_1px_rgba(47,123,255,0.08)]'
                  : 'text-crt-fg-dim hover:text-crt-fg hover:bg-crt-bg-elevated border-l-2 border-transparent'
              }`
            }
            onClick={closeMobileMenu}
          >
            <item.icon size={14} strokeWidth={1.5} />
            {!collapsed && <span>{item.label}</span>}
          </NavLink>
        ))}
      </nav>

      {/* ---- Session History ---- */}
      {!collapsed && (
        <div className="flex flex-col flex-1 overflow-hidden">
          <div className="flex items-center justify-between px-3 h-9 border-b border-crt-border">
            <span className="font-label text-[9px] text-crt-fg-muted">
              历史会话
            </span>
            <button
              onClick={handleNewSession}
              className="text-crt-fg-dim hover:text-crt-green transition-colors"
              title="新建会话"
              aria-label="新建会话"
            >
              <Plus size={14} />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto">
            {sessions.map((s) => (
              <div
                key={s.id}
                className={`group flex items-center gap-1.5 px-3 h-7 cursor-pointer transition-colors text-[11px] ${
                  s.id === currentSessionId
                    ? 'bg-crt-bg-panel text-crt-fg'
                    : 'text-crt-fg-dim hover:bg-crt-bg-elevated hover:text-crt-fg'
                }`}
                onClick={() => {
                  setSessionId(s.id);
                  clearMessages();
                }}
              >
                <span className="truncate flex-1 font-mono">
                  {s.label.replace(/^SESSION/i, '会话')}
                </span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDeleteSession(s.id);
                  }}
                  className="opacity-0 group-hover:opacity-100 text-crt-fg-muted hover:text-crt-red transition-all"
                  title="删除会话"
                  aria-label="删除会话"
                >
                  <Trash2 size={11} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ---- Footer ---- */}
      <div className="border-t border-crt-border px-3 py-2">
        {!collapsed && (
          <div className="font-label text-[8px] text-crt-fg-muted leading-tight">
            版本 1.0 · {new Date().getFullYear()}<br />
            AI 网关控制台
          </div>
        )}
      </div>
    </aside>
    </>
  );
}
