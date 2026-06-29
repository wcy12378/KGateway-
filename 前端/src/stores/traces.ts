/**
 * Trace 页面状态仓库。
 *
 * 本文件负责保存 trace 列表、分页、筛选条件和展开行状态。它不负责拉取接口、
 * 渲染表格或采集后端 trace。
 */
import { create } from 'zustand';
import type { TraceRecord, Department } from '@/types';

export interface TracesFilters {
  traceIdSearch: string;
  departments: Department[];
  cacheFilter: 'all' | 'hit' | 'miss';
  modelFilter: string;
  sortDirection: 'asc' | 'desc';
}

interface TracesState {
  traces: TraceRecord[];
  total: number;
  limit: number;
  offset: number;
  filters: TracesFilters;
  expandedTraceId: string | null;
}

interface TracesActions {
  setTraces: (traces: TraceRecord[], total: number) => void;
  setOffset: (offset: number) => void;
  setFilters: (filters: Partial<TracesFilters>) => void;
  setExpandedTraceId: (id: string | null) => void;
}

export const useTracesStore = create<TracesState & TracesActions>((set) => ({
  traces: [],
  total: 0,
  limit: 20,
  offset: 0,
  filters: {
    traceIdSearch: '',
    departments: [],
    cacheFilter: 'all',
    modelFilter: '',
    sortDirection: 'desc',
  },
  expandedTraceId: null,

  setTraces: (traces, total) => set({ traces, total }),
  setOffset: (offset) => set({ offset }),
  setFilters: (filters) =>
    set((s) => ({ filters: { ...s.filters, ...filters } })),
  setExpandedTraceId: (id) => set({ expandedTraceId: id }),
}));
