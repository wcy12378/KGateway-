/**
 * 应用主布局。
 *
 * 本文件负责组合侧边栏、顶部状态区域和页面出口。它不负责具体页面数据获取、
 * 聊天状态管理或后端接口契约。
 */
import { Outlet } from 'react-router-dom';
import { Menu } from 'lucide-react';
import { Sidebar } from '@/components/Sidebar';
import { useUIStore } from '@/stores/ui';

export function AppLayout() {
  const sidebarCollapsed = useUIStore((s) => s.sidebarCollapsed);
  const openMobileMenu = useUIStore((s) => s.openMobileMenu);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-crt-bg text-crt-fg">
      {/* Left: collapsible sidebar */}
      <Sidebar />

      {/* Right: asymmetric grid page container */}
      <main
        className="flex-1 overflow-y-auto"
        style={{
          marginLeft: 0,
        }}
      >
        {/* Top bar — breadcrumbs + status */}
        <header className="sticky top-0 z-40 flex items-center h-12 px-3 sm:px-5 border-b border-crt-border bg-crt-bg/85 backdrop-blur-md">
          <button
            onClick={openMobileMenu}
            className="mr-3 inline-flex text-crt-fg-dim hover:text-crt-fg md:hidden"
            aria-label="打开导航"
          >
            <Menu size={18} />
          </button>
          <span className="font-label text-[9px] text-crt-fg-muted tracking-[0.15em]">
            KAGENT / 企业 AI AGENT 平台
          </span>
          <div className="ml-auto flex items-center gap-4">
            <span className="font-label text-[9px] text-crt-fg-muted">
              控制台已启动
            </span>
            <span className="inline-block w-2 h-2 rounded-full bg-crt-green shadow-[0_0_16px_rgba(50,213,131,0.7)]" />
          </div>
        </header>

        {/* Page content — asymmetric grid */}
        <div className="p-3 sm:p-5">
          <div
            className="grid gap-px"
            style={{
              gridTemplateColumns: sidebarCollapsed
                ? '1fr'
                : 'minmax(0, 1fr)',
            }}
          >
            <Outlet />
          </div>
        </div>
      </main>
    </div>
  );
}
