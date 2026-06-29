/**
 * 全局 UI 状态仓库。
 *
 * 本文件负责保存主题和侧边栏折叠状态。它不负责页面数据、聊天状态或后端接口。
 */
import { create } from 'zustand';

type Theme = 'dark' | 'light';

interface UIState {
  sidebarCollapsed: boolean;
  mobileMenuOpen: boolean;
  theme: Theme;
}

interface UIActions {
  toggleSidebar: () => void;
  setSidebarCollapsed: (v: boolean) => void;
  openMobileMenu: () => void;
  closeMobileMenu: () => void;
  setTheme: (t: Theme) => void;
  toggleTheme: () => void;
}

export const useUIStore = create<UIState & UIActions>((set) => ({
  sidebarCollapsed: false,
  mobileMenuOpen: false,
  theme: 'dark',

  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  setSidebarCollapsed: (v) => set({ sidebarCollapsed: v }),
  openMobileMenu: () => set({ mobileMenuOpen: true }),
  closeMobileMenu: () => set({ mobileMenuOpen: false }),
  setTheme: (t) => set({ theme: t }),
  toggleTheme: () =>
    set((s) => ({ theme: s.theme === 'dark' ? 'light' : 'dark' })),
}));
