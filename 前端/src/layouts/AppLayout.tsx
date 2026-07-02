import { Outlet, useLocation } from 'react-router-dom';
import { Menu } from 'lucide-react';
import { Sidebar } from '@/components/Sidebar';
import { useUIStore } from '@/stores/ui';

export function AppLayout() {
  const openMobileMenu = useUIStore((s) => s.openMobileMenu);
  const isChat = useLocation().pathname === '/';

  return <div className="flex min-h-[100dvh] w-full bg-white text-crt-fg">
    <Sidebar />
    <main className="min-w-0 flex-1 bg-white">
      <header className="sticky top-0 z-30 flex h-14 items-center border-b border-crt-border bg-white px-4 md:hidden">
        <button onClick={openMobileMenu} className="icon-button mr-3" aria-label="打开导航"><Menu size={17} /></button>
        <span className="text-[12px] font-medium text-crt-fg-dim">KAgent 企业智能工作台</span>
        <span className="ml-auto h-2 w-2 rounded-full bg-crt-green" aria-label="服务在线" />
      </header>
      <div className={isChat ? 'p-0' : 'p-4 sm:p-6 lg:p-8'}>
        <div className={isChat ? 'w-full' : 'page-shell'}><Outlet /></div>
      </div>
    </main>
  </div>;
}
