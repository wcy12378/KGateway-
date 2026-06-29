/**
 * 熔断器页面状态仓库。
 *
 * 本文件负责保存熔断器统计快照。它不负责调用后端接口、执行业务操作或展示 UI。
 */
import { create } from 'zustand';
import type { CircuitBreakerStats } from '@/types';

interface BreakerState {
  stats: CircuitBreakerStats | null;
  isOperating: boolean;
}

interface BreakerActions {
  setStats: (s: CircuitBreakerStats) => void;
  setOperating: (v: boolean) => void;
}

export const useBreakerStore = create<BreakerState & BreakerActions>((set) => ({
  stats: null,
  isOperating: false,

  setStats: (stats) => set({ stats }),
  setOperating: (v) => set({ isOperating: v }),
}));
