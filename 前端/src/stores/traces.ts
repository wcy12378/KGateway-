/**
 * Trace 页面状态仓库。
 *
 * 本文件负责保存 trace 列表、分页、筛选条件和展开行状态。它不负责拉取接口、
 * 渲染表格或采集后端 trace。
 */
import { create } from 'zustand';
import type { Department } from '@/types';

export interface TracesFilters {
  traceIdSearch: string;
  departments: Department[];
  cacheFilter: 'all' | 'hit' | 'miss';
  modelFilter: string;
  sortDirection: 'asc' | 'desc';
}

interface TracesState {
  offset: number;
  filters: TracesFilters;
  expandedTraceId: string | null;
}

interface TracesActions {
  setOffset: (offset: number) => void;
  setFilters: (filters: Partial<TracesFilters>) => void;
  setExpandedTraceId: (id: string | null) => void;
}

export const useTracesStore = create<TracesState & TracesActions>((set) => ({
  offset: 0,
  filters: {
    traceIdSearch: '',
    departments: [],
    cacheFilter: 'all',
    modelFilter: '',
    sortDirection: 'desc',
  },
  expandedTraceId: null,

  setOffset: (offset) => set({ offset }),
  setFilters: (filters) =>
    set((s) => ({ filters: { ...s.filters, ...filters }, offset: 0 })),
  setExpandedTraceId: (id) => set({ expandedTraceId: id }),
}));
