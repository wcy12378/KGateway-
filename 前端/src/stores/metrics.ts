/**
 * 指标看板状态仓库。
 *
 * 本文件负责保存 metrics 快照和刷新间隔。它不负责调用监控接口或渲染图表。
 */
import { create } from 'zustand';
import type { MetricsSnapshot } from '@/types';

interface MetricsState {
  snapshot: MetricsSnapshot | null;
  refreshInterval: number; // ms, 0 = off
}

interface MetricsActions {
  setSnapshot: (s: MetricsSnapshot) => void;
  setRefreshInterval: (ms: number) => void;
}

export const useMetricsStore = create<MetricsState & MetricsActions>((set) => ({
  snapshot: null,
  refreshInterval: 5000,

  setSnapshot: (snapshot) => set({ snapshot }),
  setRefreshInterval: (ms) => set({ refreshInterval: ms }),
}));
