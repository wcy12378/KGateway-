/**
 * Trace 分页组件。
 *
 * 本文件负责展示当前 trace 分页范围和翻页按钮。它不负责过滤、排序或拉取
 * 后端 trace 数据。
 */
interface TracePaginationProps {
  offset: number;
  pageSize: number;
  total: number;
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}

export function TracePagination({
  offset,
  pageSize,
  total,
  currentPage,
  totalPages,
  onPageChange,
}: TracePaginationProps) {
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between mt-3 font-label text-crt-fg-muted">
      <span>
        显示 {total > 0 ? offset + 1 : 0}-
        {Math.min(offset + pageSize, total)} / {total}
      </span>
      <div className="flex items-center gap-2">
        <button
          disabled={currentPage <= 1}
          onClick={() => onPageChange(currentPage - 1)}
          className="px-3 py-1.5 border border-crt-border text-crt-fg-dim hover:border-crt-border-strong hover:text-crt-fg transition-colors disabled:opacity-20 disabled:cursor-not-allowed rounded-md"
        >
          上一页
        </button>
        <span className="px-3 py-1 text-crt-fg">
          第 {currentPage} / {totalPages} 页
        </span>
        <button
          disabled={currentPage >= totalPages}
          onClick={() => onPageChange(currentPage + 1)}
          className="px-3 py-1.5 border border-crt-border text-crt-fg-dim hover:border-crt-border-strong hover:text-crt-fg transition-colors disabled:opacity-20 disabled:cursor-not-allowed rounded-md"
        >
          下一页
        </button>
      </div>
    </div>
  );
}
