/**
 * Trace 过滤控件组件。
 *
 * 本文件负责渲染 trace 搜索、部门、缓存、模型和排序控件。它不负责拉取数据、
 * 执行过滤算法或渲染 trace 表格。
 */
import { TRACE_DEPARTMENTS } from '@/lib/traces';
import type { TracesFilters } from '@/stores/traces';
import type { Department } from '@/types';

const DEPARTMENT_LABELS: Record<Department, string> = {
  legal: '法务',
  hr: '人力',
  engineering: '工程',
  finance: '财务',
  general: '通用',
};

interface TraceFiltersProps {
  filters: TracesFilters;
  onChange: (filters: Partial<TracesFilters>) => void;
}

export function TraceFilters({ filters, onChange }: TraceFiltersProps) {
  const toggleDepartment = (department: Department) => {
    onChange({
      departments: filters.departments.includes(department)
        ? filters.departments.filter((item) => item !== department)
        : [...filters.departments, department],
    });
  };

  return (
    <div className="flex gap-2 mb-4 flex-wrap rounded-lg border border-crt-border bg-crt-bg-elevated p-3">
      <input
        value={filters.traceIdSearch}
        onChange={(event) => onChange({ traceIdSearch: event.target.value })}
        className="flex-1 min-w-[200px] bg-crt-bg border border-crt-border text-crt-fg text-[12px] font-mono px-3 py-2 placeholder:text-crt-fg-muted focus:outline-none focus:border-crt-border-strong"
        placeholder="搜索 trace_id"
      />

      <div className="flex gap-1">
        {TRACE_DEPARTMENTS.map((department) => (
          <button
            key={department}
            onClick={() => toggleDepartment(department)}
            className={`px-2 py-1.5 border font-label tracking-widest transition-colors rounded-md ${
              filters.departments.includes(department)
                ? 'border-crt-fg text-crt-fg bg-crt-bg-panel'
                : 'border-crt-border text-crt-fg-muted hover:border-crt-fg-dim'
            }`}
          >
            {DEPARTMENT_LABELS[department]}
          </button>
        ))}
      </div>

      <select
        value={filters.cacheFilter}
        onChange={(event) =>
          onChange({
            cacheFilter: event.target.value as 'all' | 'hit' | 'miss',
          })
        }
        className="bg-crt-bg border border-crt-border text-crt-fg text-[12px] font-mono px-2 py-2 focus:outline-none focus:border-crt-border-strong"
      >
        <option value="all">全部缓存</option>
        <option value="hit">仅命中</option>
        <option value="miss">仅未命中</option>
      </select>

      <input
        value={filters.modelFilter}
        onChange={(event) => onChange({ modelFilter: event.target.value })}
        className="w-32 bg-crt-bg border border-crt-border text-crt-fg text-[12px] font-mono px-2 py-2 placeholder:text-crt-fg-muted focus:outline-none focus:border-crt-border-strong"
        placeholder="模型"
      />

      <button
        onClick={() =>
          onChange({
            sortDirection: filters.sortDirection === 'desc' ? 'asc' : 'desc',
          })
        }
        className="px-2 py-1.5 border border-crt-border text-crt-fg-dim font-label tracking-widest hover:border-crt-border-strong hover:text-crt-fg transition-colors rounded-md"
        aria-label="切换延迟排序"
        title="切换延迟排序"
      >
        延迟 {filters.sortDirection === 'desc' ? '降序' : '升序'}
      </button>
    </div>
  );
}
